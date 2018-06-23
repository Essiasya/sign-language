"""
Classify human motion videos 
"""

import os
import glob
import sys
import warnings
import time

import numpy as np
import pandas as pd

import keras

from datagenerator import VideoClasses, FeaturesGenerator


def predict(arFeatures:np.array(float), keModel:keras.Model, oClasses:VideoClasses, nTop:int = 3) -> (int, str, float):
    """ Run the features (of the frames of the video) of 1 sample through LSTM to predict video
    # Return
        3-tuple: predicted nLabel, sLabel, fProbability
        in addition print nTop most probable labels
    """

    if keModel.input_shape[1:] != arFeatures.shape: raise ValueError("Incorrect shapes")

    # infer on network
    arX = np.expand_dims(arFeatures, axis=0)
    print("Predict video category with %s ..." % (keModel.name))
    arProbas = keModel.predict(arX, verbose = 1)[0]

    arTopLabels = arProbas.argsort()[-nTop:][::-1]
    arTopProbas = arProbas[arTopLabels]


    for i in range(nTop):
        sClass = oClasses.dfClass.sClass[arTopLabels[i]] + " " + oClasses.dfClass.sDetail[arTopLabels[i]]
        print("Top %d: [%3d] %s (confidence %.0f%%)" % \
            (i+1, arTopLabels[i], sClass, arTopProbas[i]*100.))
        
    sClass = oClasses.dfClass.sClass[arTopLabels[0]] + " " + oClasses.dfClass.sDetail[arTopLabels[0]]
    return arTopLabels[0], sClass, arTopProbas[0]




def predict_generator(sFeatureDir:str, sModelPath:str, oClasses:VideoClasses, nBatchSize:int = 16):    
    """ Predict labels for all features in given directory on saved model 
    
    Returns 
        fAccuracy
        arPredictions (dim = nSamples)
        arProbabilities (dim = (nSamples, nClasses)) 
        list of labels (groundtruth)
    """
        
    # load the I3D top network
    print("Load model %s ..." % sModelPath)
    keModel = keras.models.load_model(sModelPath)

    # Load video features
    genFeatures = FeaturesGenerator(sFeatureDir, nBatchSize,
        keModel.input_shape[1:], oClasses.liClasses, bShuffle = False)
    if genFeatures.nSamples == 0: raise ValueError("No feature files detected, prediction stopped")

    # predict
    print("Predict with generator on %s ..." % sFeatureDir)
    arProba = keModel.predict_generator(
        generator = genFeatures, 
        workers = 1,                 
        use_multiprocessing = False,
        verbose = 1)
    if arProba.shape[0] != genFeatures.nSamples: raise ValueError("Unexpected number of predictions")

    arPred = arProba.argmax(axis=1)
    liLabels = list(genFeatures.dfSamples.sLabel)
    fAcc = np.mean(liLabels == oClasses.dfClass.loc[arPred, "sClass"])
    
    return fAcc, arPred, arProba, liLabels


def main():
   
    # important constants
    nClasses = 21   # number of classes
    nFrames = 20    # number of frames per video

    # feature extractor 
    diFeature = {"sName" : "mobilenet",
        "tuInputShape" : (224, 224, 3),
        "tuOutputShape" : (1024, )}
    #diFeature = {"sName" : "inception",
    #    "tuInputShape" : (299, 299, 3),
    #    "nOutput" : 2048}

    # directories
    sClassFile       = "data-set/01-ledasila/%03d/class.csv"%(nClasses)
    #sVideoDir        = "data-set/01-ledasila/%03d"%(nClasses)
    #sImageDir        = "data-temp/01-ledasila/%03d/image"%(nClasses)
    sImageFeatureDir = "data-temp/01-ledasila/%03d/image-mobilenet/val"%(nClasses)
    #sOflowDir        = "data-temp/01-ledasila/%03d/oflow"%(nClasses)
    sOflowFeatureDir = "data-temp/01-ledasila/%03d/oflow-mobilenet/val"%(nClasses)

    sModelDir        = "model"
    sModelImageBest  = sModelDir + "/20180620-1653-ledasila021-image-mobile-lstm-best.h5"
    sModelImageLast  = sModelDir + "/20180620-1653-ledasila021-image-mobile-lstm-last.h5"
    sModelOflowBest  = sModelDir + "/20180620-1701-ledasila021-oflow-mobile-lstm-best.h5"
    sModelOflowLast  = sModelDir + "/20180620-1701-ledasila021-oflow-mobile-lstm-last.h5"


    print("\nPredict with combined rgb + flow models ... ")
    print(os.getcwd())
    
    # initialize
    oClasses = VideoClasses(sClassFile)

    # predict on image features
    fAcc_image_best, _, arProba_image_best, liLabels_image_best = \
        predict_generator(sImageFeatureDir, sModelImageBest, oClasses)
    print("Image best model accuracy: %.2f%%"%(fAcc_image_best*100.))

    fAcc_image_last, _, arProba_image_last, liLabels_image_last = \
        predict_generator(sImageFeatureDir, sModelImageLast, oClasses)
    print("Image last model accuracy: %.2f%%"%(fAcc_image_last*100.))

    # predict on flow features
    fAcc_oflow_best, _, arProba_oflow_best, liLabels_oflow_best = \
        predict_generator(sOflowFeatureDir, sModelOflowBest, oClasses)
    print("Optical flow best model accuracy: %.2f%%"%(fAcc_oflow_best*100.))

    fAcc_oflow_last, _, arProba_oflow_last, liLabels_oflow_last = \
        predict_generator(sOflowFeatureDir, sModelOflowLast, oClasses)
    print("Optical flow last model accuracy: %.2f%%"%(fAcc_oflow_last*100.))

    # Combine predicted probabilities, first check if labels are equal
    if liLabels_image_best != liLabels_oflow_best:
        raise ValueError("The rgb and flwo labels do not match")

    # only last models
    arSoftmax = arProba_image_last + arProba_oflow_last # shape = (nSamples, nClasses)
    arProba = np.exp(arSoftmax) / np.sum(np.exp(arSoftmax), axis=1).reshape(-1,1)
    arPred = arProba.argmax(axis=1)
    fAcc = np.mean(liLabels_image_best == oClasses.dfClass.loc[arPred, "sClass"])
    print("\nLast image & last optical flow model combined accuracy: %.2f%%"%(fAcc*100.))

    # only flow models together
    arSoftmax = arProba_oflow_best + arProba_oflow_last # shape = (nSamples, nClasses)
    arProba = np.exp(arSoftmax) / np.sum(np.exp(arSoftmax), axis=1).reshape(-1,1)
    arPred = arProba.argmax(axis=1)
    fAcc = np.mean(liLabels_image_best == oClasses.dfClass.loc[arPred, "sClass"])
    print("\nCombined 2 optical flow model accuracy: %.2f%%"%(fAcc*100.))

    # average over all 4 models
    arSoftmax = arProba_image_best + arProba_image_last + arProba_oflow_best + arProba_oflow_last # shape = (nSamples, nClasses)
    arProba = np.exp(arSoftmax) / np.sum(np.exp(arSoftmax), axis=1).reshape(-1,1)
    arPred = arProba.argmax(axis=1)
    fAcc = np.mean(liLabels_image_best == oClasses.dfClass.loc[arPred, "sClass"])
    print("\nCombined 4-model accuracy: %.2f%%"%(fAcc*100.))

    return


if __name__ == '__main__':
    main()