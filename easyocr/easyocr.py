# -*- coding: utf-8 -*-

from .detection import get_detector, get_textbox
from .recognition import get_recognizer, get_text
from .utils import group_text_box, get_image_list, calculate_md5, get_paragraph,\
                   download_and_unzip, printProgressBar, diff, reformat_input,\
                   make_rotated_img_list, set_result_with_confidence
from .config import *
from bidi.algorithm import get_display
import numpy as np
import cv2
import torch
import os
import sys
from PIL import Image
from logging import getLogger
import yaml

if sys.version_info[0] == 2:
    from io import open
    from six.moves.urllib.request import urlretrieve
    from pathlib2 import Path
else:
    from urllib.request import urlretrieve
    from pathlib import Path

LOGGER = getLogger(__name__)

class Reader(object):

    def __init__(self, lang_list, gpu=True, model_storage_directory=None,
                 user_network_directory=None, recog_network = 'standard',
                 download_enabled=True, detector=True, recognizer=True):
        """Create an EasyOCR Reader.

        Parameters:
            lang_list (list): Language codes (ISO 639) for languages to be recognized during analysis.

            gpu (bool): Enable GPU support (default)

            model_storage_directory (string): Path to directory for model data. If not specified,
            models will be read from a directory as defined by the environment variable
            EASYOCR_MODULE_PATH (preferred), MODULE_PATH (if defined), or ~/.EasyOCR/.

            user_network_directory (string): Path to directory for custom network architecture.
            If not specified, it is as defined by the environment variable
            EASYOCR_MODULE_PATH (preferred), MODULE_PATH (if defined), or ~/.EasyOCR/.

            download_enabled (bool): Enabled downloading of model data via HTTP (default).
        """
        self.download_enabled = download_enabled

        self.model_storage_directory = MODULE_PATH + '/model'
        if model_storage_directory:
            self.model_storage_directory = model_storage_directory
        Path(self.model_storage_directory).mkdir(parents=True, exist_ok=True)

        self.user_network_directory = MODULE_PATH + '/user_network'
        if user_network_directory:
            self.user_network_directory = user_network_directory
        Path(self.user_network_directory).mkdir(parents=True, exist_ok=True)
        sys.path.append(self.user_network_directory)

        if gpu is False:
            self.device = 'cpu'
            LOGGER.warning('Using CPU. Note: This module is much faster with a GPU.')
        elif not torch.cuda.is_available():
            self.device = 'cpu'
            LOGGER.warning('CUDA not available - defaulting to CPU. Note: This module is much faster with a GPU.')
        elif gpu is True:
            self.device = 'cuda'
        else:
            self.device = gpu

        # check and download detection model
        corrupt_msg = 'MD5 hash mismatch, possible file corruption'
        detector_path = os.path.join(self.model_storage_directory, DETECTOR_FILENAME)
        if detector:
            if os.path.isfile(detector_path) == False:
                if not self.download_enabled:
                    raise FileNotFoundError("Missing %s and downloads disabled" % detector_path)
                LOGGER.warning('Downloading detection model, please wait. '
                               'This may take several minutes depending upon your network connection.')
                download_and_unzip(model_url['detector'][0], DETECTOR_FILENAME, self.model_storage_directory)
                assert calculate_md5(detector_path) == model_url['detector'][1], corrupt_msg
                LOGGER.info('Download complete')
            elif calculate_md5(detector_path) != model_url['detector'][1]:
                if not self.download_enabled:
                    raise FileNotFoundError("MD5 mismatch for %s and downloads disabled" % detector_path)
                LOGGER.warning(corrupt_msg)
                os.remove(detector_path)
                LOGGER.warning('Re-downloading the detection model, please wait. '
                               'This may take several minutes depending upon your network connection.')
                download_and_unzip(model_url['detector'][0], DETECTOR_FILENAME, self.model_storage_directory)
                assert calculate_md5(detector_path) == model_url['detector'][1], corrupt_msg

        # recognition model
        separator_list = {}
        if recog_network != 'standard':
            with open(os.path.join(self.user_network_directory, recog_network+ '.yaml')) as file:
                recog_config = yaml.load(file, Loader=yaml.FullLoader)
            imgH = recog_config['imgH']
            available_lang = recog_config['lang_list']
            self.setModelLanguage(recog_network, lang_list, available_lang, available_lang)
            char_file = os.path.join(self.user_network_directory, recog_network+ '.txt')
            self.character = recog_config['character_list']
            model_file = recog_network+ '.pth'
            model_path = os.path.join(self.model_storage_directory, model_file)
        else:
            # check available languages
            unknown_lang = set(lang_list) - set(all_lang_list)
            if unknown_lang != set():
                raise ValueError(unknown_lang, 'is not supported')

            # choose recognition model
            if 'th' in lang_list:
                self.setModelLanguage('thai', lang_list, ['th','en'], '["th","en"]')
            elif 'ch_tra' in lang_list:
                self.setModelLanguage('chinese_tra', lang_list, ['ch_tra','en'], '["ch_tra","en"]')
            elif 'ch_sim' in lang_list:
                self.setModelLanguage('chinese_sim', lang_list, ['ch_sim','en'], '["ch_sim","en"]')
            elif 'ja' in lang_list:
                self.setModelLanguage('japanese', lang_list, ['ja','en'], '["ja","en"]')
            elif 'ko' in lang_list:
                self.setModelLanguage('korean', lang_list, ['ko','en'], '["ko","en"]')
            elif 'ta' in lang_list:
                self.setModelLanguage('tamil', lang_list, ['ta','en'], '["ta","en"]')
            elif 'te' in lang_list:
                self.setModelLanguage('telugu', lang_list, ['te','en'], '["te","en"]')
            elif 'kn' in lang_list:
                self.setModelLanguage('kannada', lang_list, ['kn','en'], '["kn","en"]')
            elif set(lang_list) & set(bengali_lang_list):
                self.setModelLanguage('bengali', lang_list, bengali_lang_list+['en'], '["bn","as","en"]')
            elif set(lang_list) & set(arabic_lang_list):
                self.setModelLanguage('arabic', lang_list, arabic_lang_list+['en'], '["ar","fa","ur","ug","en"]')
            elif set(lang_list) & set(devanagari_lang_list):
                self.setModelLanguage('devanagari', lang_list, devanagari_lang_list+['en'], '["hi","mr","ne","en"]')
            elif set(lang_list) & set(cyrillic_lang_list):
                self.setModelLanguage('cyrillic', lang_list, cyrillic_lang_list+['en'],
                                      '["ru","rs_cyrillic","be","bg","uk","mn","en"]')
            else: self.model_lang = 'latin'

            if self.model_lang == 'latin':
                self.character = number+ symbol + characters['all_char']
                model_file = 'latin.pth'
            elif self.model_lang == 'arabic':
                self.character = number + symbol + characters['en_char'] + characters['ar_number'] + characters['ar_symbol'] + characters['ar_char']
                model_file = 'arabic.pth'
            elif self.model_lang == 'cyrillic':
                self.character = number+ symbol + characters['en_char'] + characters['cyrillic_char']
                model_file = 'cyrillic.pth'
            elif self.model_lang == 'devanagari':
                self.character = number+ symbol + characters['en_char'] + characters['devanagari_char']
                model_file = 'devanagari.pth'
            elif self.model_lang == 'bengali':
                self.character = number+ symbol + characters['en_char'] + characters['bn_char']
                model_file = 'bengali.pth'
            elif  self.model_lang == 'chinese_tra':
                ch_tra_char = self.getChar("ch_tra_char.txt")
                self.character = number + symbol + characters['en_char'] + ch_tra_char
                model_file = 'chinese.pth'
            elif  self.model_lang == 'chinese_sim':
                ch_sim_char = self.getChar("ch_sim_char.txt")
                self.character = number + symbol + characters['en_char'] + ch_sim_char
                model_file = 'chinese_sim.pth'
            elif  self.model_lang == 'japanese':
                ja_char = self.getChar("ja_char.txt")
                self.character = number + symbol + characters['en_char'] + ja_char
                model_file = 'japanese.pth'
            elif  self.model_lang == 'korean':
                ko_char = self.getChar("ko_char.txt")
                self.character = number + symbol + characters['en_char'] + ko_char
                model_file = 'korean.pth'
            elif  self.model_lang == 'tamil':
                ta_char = self.getChar("ta_char.txt")
                self.character = number + symbol + characters['en_char'] + ta_char
                model_file = 'tamil.pth'
            elif  self.model_lang == 'telugu':
                self.character = number + symbol + characters['en_char'] + characters['te_char']
                model_file = 'telugu.pth'
                recog_network = 'lite'
            elif  self.model_lang == 'kannada':
                self.character = number + symbol + characters['en_char'] + characters['kn_char']
                model_file = 'kannada.pth'
                recog_network = 'lite'
            elif self.model_lang == 'thai':
                separator_list = {
                    'th': ['\xa2', '\xa3'],
                    'en': ['\xa4', '\xa5']
                }
                separator_char = []
                for lang, sep in separator_list.items():
                    separator_char += sep
                self.character = ''.join(separator_char) + symbol + characters['en_char'] + characters['th_char'] + characters['th_number']
                model_file = 'thai.pth'
            else:
                LOGGER.error('invalid language')

            model_path = os.path.join(self.model_storage_directory, model_file)
            # check recognition model file
            if recognizer:
                if os.path.isfile(model_path) == False:
                    if not self.download_enabled:
                        raise FileNotFoundError("Missing %s and downloads disabled" % model_path)
                    LOGGER.warning('Downloading recognition model, please wait. '
                                   'This may take several minutes depending upon your network connection.')
                    download_and_unzip(model_url[model_file][0], model_file, self.model_storage_directory)
                    assert calculate_md5(model_path) == model_url[model_file][1], corrupt_msg
                    LOGGER.info('Download complete.')
                elif calculate_md5(model_path) != model_url[model_file][1]:
                    if not self.download_enabled:
                        raise FileNotFoundError("MD5 mismatch for %s and downloads disabled" % model_path)
                    LOGGER.warning(corrupt_msg)
                    os.remove(model_path)
                    LOGGER.warning('Re-downloading the recognition model, please wait. '
                                   'This may take several minutes depending upon your network connection.')
                    download_and_unzip(model_url[model_file][0], model_file, self.model_storage_directory)
                    assert calculate_md5(model_path) == model_url[model_file][1], corrupt_msg
                    LOGGER.info('Download complete')

        self.setLanguageList(lang_list)

        dict_list = {}
        for lang in lang_list:
            dict_list[lang] = os.path.join(BASE_PATH, 'dict', lang + ".txt")

        if detector:
            self.detector = get_detector(detector_path, self.device)
        if recognizer:
            if recog_network == 'standard':
                network_params = {
                    'input_channel': 1,
                    'output_channel': 512,
                    'hidden_size': 512
                    }
            elif recog_network == 'lite':
                network_params = {
                    'input_channel': 1,
                    'output_channel': 256,
                    'hidden_size': 256
                    }
            else:
                network_params = recog_config['network_params']
            self.recognizer, self.converter = get_recognizer(recog_network, network_params,\
                                                         self.character, separator_list,\
                                                         dict_list, model_path, device = self.device)

    def setModelLanguage(self, language, lang_list, list_lang, list_lang_string):
        self.model_lang = language
        if set(lang_list) - set(list_lang) != set():
            if language == 'ch_tra' or language == 'ch_sim':
                language = 'chinese'
            raise ValueError(language.capitalize() + ' is only compatible with English, try lang_list=' + list_lang_string)

    def getChar(self, fileName):
        char_file = os.path.join(BASE_PATH, 'character', fileName)
        with open(char_file, "r", encoding="utf-8-sig") as input_file:
            list = input_file.read().splitlines()
            char = ''.join(list)
        return char

    def setLanguageList(self, lang_list):
        self.lang_char = []
        for lang in lang_list:
            char_file = os.path.join(BASE_PATH, 'character', lang + "_char.txt")
            with open(char_file, "r", encoding = "utf-8-sig") as input_file:
                char_list =  input_file.read().splitlines()
            self.lang_char += char_list
        self.lang_char = set(self.lang_char).union(set(number+symbol))
        self.lang_char = ''.join(self.lang_char)

    def detect(self, img, min_size = 20, text_threshold = 0.7, low_text = 0.4,\
               link_threshold = 0.4,canvas_size = 2560, mag_ratio = 1.,\
               slope_ths = 0.1, ycenter_ths = 0.5, height_ths = 0.5,\
               width_ths = 0.5, add_margin = 0.1, reformat=True, optimal_num_chars=None):

        if reformat:
            img, img_cv_grey = reformat_input(img)

        text_box = get_textbox(self.detector, img, canvas_size, mag_ratio,\
                               text_threshold, link_threshold, low_text,\
                               False, self.device, optimal_num_chars)
        horizontal_list, free_list = group_text_box(text_box, slope_ths,\
                                                    ycenter_ths, height_ths,\
                                                    width_ths, add_margin, \
                                                    (optimal_num_chars is None))

        if min_size:
            horizontal_list = [i for i in horizontal_list if max(i[1]-i[0],i[3]-i[2]) > min_size]
            free_list = [i for i in free_list if max(diff([c[0] for c in i]), diff([c[1] for c in i]))>min_size]

        return horizontal_list, free_list

    def recognize(self, img_cv_grey, horizontal_list=None, free_list=None,\
                  decoder = 'greedy', beamWidth= 5, batch_size = 1,\
                  workers = 0, allowlist = None, blocklist = None, detail = 1,\
                  rotation_info = None,\
                  paragraph = False,\
                  contrast_ths = 0.1,adjust_contrast = 0.5, filter_ths = 0.003,\
                  reformat=True):

        if reformat:
            img, img_cv_grey = reformat_input(img_cv_grey)

        if (horizontal_list==None) and (free_list==None):
            y_max, x_max = img_cv_grey.shape
            ratio = x_max/y_max
            max_width = int(imgH*ratio)
            crop_img = cv2.resize(img_cv_grey, (max_width, imgH), interpolation =  Image.ANTIALIAS)
            image_list = [([[0,0],[x_max,0],[x_max,y_max],[0,y_max]] ,crop_img)]
        else:
            image_list, max_width = get_image_list(horizontal_list, free_list, img_cv_grey, model_height = imgH)

        if allowlist:
            ignore_char = ''.join(set(self.character)-set(allowlist))
        elif blocklist:
            ignore_char = ''.join(set(blocklist))
        else:
            ignore_char = ''.join(set(self.character)-set(self.lang_char))

        image_len = len(image_list)
        if rotation_info and image_list:
            image_list = make_rotated_img_list(rotation_info, image_list)

        if self.model_lang in ['chinese_tra','chinese_sim', 'japanese', 'korean']: decoder = 'greedy'
        result = get_text(self.character, imgH, int(max_width), self.recognizer, self.converter, image_list,\
                      ignore_char, decoder, beamWidth, batch_size, contrast_ths, adjust_contrast, filter_ths,\
                      workers, self.device)

        if self.model_lang == 'arabic':
            direction_mode = 'rtl'
            result = [list(item) for item in result]
            for item in result:
                item[1] = get_display(item[1])
        else:
            direction_mode = 'ltr'

        if paragraph:
            result = get_paragraph(result, mode = direction_mode)

        if rotation_info and image_list:
            result = set_result_with_confidence(result, image_len)

        if detail == 0:
            return [item[1] for item in result]
        else:
            return result

    def readtext(self, image, decoder = 'greedy', beamWidth= 5, batch_size = 1,\
                 workers = 0, allowlist = None, blocklist = None, detail = 1,\
                 rotation_info = None, paragraph = False, min_size = 20,\
                 contrast_ths = 0.1,adjust_contrast = 0.5, filter_ths = 0.003,\
                 text_threshold = 0.7, low_text = 0.4, link_threshold = 0.4,\
                 canvas_size = 2560, mag_ratio = 1.,\
                 slope_ths = 0.1, ycenter_ths = 0.5, height_ths = 0.5,\
                 width_ths = 0.5, add_margin = 0.1):
        '''
        Parameters:
        image: file path or numpy-array or a byte stream object
        '''
        img, img_cv_grey = reformat_input(image)

        horizontal_list, free_list = self.detect(img, min_size, text_threshold,\
                                                 low_text, link_threshold,\
                                                 canvas_size, mag_ratio,\
                                                 slope_ths, ycenter_ths,\
                                                 height_ths,width_ths,\
                                                 add_margin, False)

        result = self.recognize(img_cv_grey, horizontal_list, free_list,\
                                decoder, beamWidth, batch_size,\
                                workers, allowlist, blocklist, detail, rotation_info,\
                                paragraph, contrast_ths, adjust_contrast,\
                                filter_ths, False)

        return result
