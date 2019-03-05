#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2018-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
#

import os, io
import sys
import copy
import re, json, collections
import numpy as np

from src.data.tokenization import BertTokenizer
from src.data.pron_dict import PronDict
from src.data.pron_dict import get_rhyme
from src.logger import create_logger

import torch
import random
random.seed(42)

MAX_SENT_LEN=130
PUNC = ['.','"',u'？',u'。',u'！',u'”']

def zng(paragraph):
    for sent in re.findall(u'.+[.。?？!！\"”]', paragraph, flags=re.U):
        yield sent

def split_train_valid(txt_path, train_prob, pron_dict, isjueju):
    train_input = []
    valid_input = []
    with io.open(txt_path, "r", encoding='utf8') as f:
        for line in f:
            s = line.rstrip()
            if len(s) != 0:
                if isjueju:
                    if len(s)>31:
                        end_sent_2_tok = s[14]
                        end_sent_4_tok = s[30]
                        if pron_dict.co_rhyme(end_sent_2_tok, end_sent_4_tok):
                            if random.random() < train_prob:
                                train_input.append(s)
                            else:
                                valid_input.append(s)
                else:
                    if random.random() < train_prob:
                        train_input.append(s)
                    else:
                        valid_input.append(s)
    print ("num train data: %d"% len(train_input))
    print ("num valid data: %d"% len(valid_input))
    return train_input, valid_input


def get_data(input_sents, tokenizer):
    positions = []
    sentences = []
    sentences_len = []
    length_in_count = np.zeros(int(MAX_SENT_LEN/10)+1)
    unk_words = {}
    line_count=0
    too_long_sent_count = 0
    long_sent_count = 0
    for ind in range(len(input_sents)):
        sent=input_sents[ind]
        # realmax_len=MAX_SENT_LEN
        realmax_len = np.random.normal(loc=99.0, scale=10.0, size=None)
        if realmax_len > MAX_SENT_LEN:
            realmax_len = MAX_SENT_LEN 
        realmax_len = int(realmax_len)

        if len(sent) > realmax_len:
            # print("Long sentence with len %i in line %i." % (len(sent),line_count))
            sent=sent[0:realmax_len]
            sent = list(zng(sent)) # ends with punc
            if len(sent) == 0:
                sent=''
                too_long_sent_count+=1
            else:
                assert len(sent)==1
                sent = sent[0]
                long_sent_count+=1
        token_s = tokenizer.tokenize(sent)
        # if len(token_s) == 0:
        #     print("Empty sentence in line %i." % line_count)
        if len(token_s) > 10:
            # index sentence words
            indexed = tokenizer.convert_tokens_to_ids(token_s)
            unk_idxs = [i for i, e in enumerate(indexed) if e == 100]
            for unk_idx in unk_idxs:
                w = sent[unk_idx] 
                unk_words[w] = unk_words.get(w, 0) + 1
            # add sentence
            positions.append([len(sentences), len(sentences) + len(indexed)])
            sentences_len.append(len(indexed))
            sentences.extend(indexed)
            sentences.append(-1)
            line_count+=1
            if len(token_s) > 130:
                length_in_count[-1] += 1
            else:
                length_in_count[int(len(token_s)/10)] += 1
        # else:
        #     print("Short sentence in line %i. <=10" % line_count)

    # tensorize data
    positions = torch.LongTensor(positions)
    sentences = torch.LongTensor(sentences)
    data = {
        'dico': tokenizer,
        'positions': positions,
        'sentences': sentences,
        'unk_words': unk_words,
    }
    print('long sentence count:')
    print(long_sent_count)
    print('long sentence that can not convert count:')
    print(too_long_sent_count)
    length_in_count = length_in_count/np.sum(length_in_count)
    print('sentence length bin count:')
    print(length_in_count)
    print('sentence length mean and std:')
    print(np.mean(sentences_len))
    print(np.std(sentences_len))
    return data


if __name__ == '__main__':

    logger = create_logger(None)

    voc_path = sys.argv[1]
    txt_path = sys.argv[2]
    bin_path_tr = sys.argv[2] + '.tr.pth'
    bin_path_vl = sys.argv[2] + '.vl.pth'
    isjueju = sys.argv[3]
    if isjueju.startswith('jue'):
        isjueju = True
    else:
        isjueju = False
    print ("is jueju?: ")
    print (isjueju)
    vocab_rytm_file = 'data/vocab_rytm.json'
    assert os.path.isfile(voc_path)
    assert os.path.isfile(txt_path)

    logger.info("")

    # get tokenizer
    if voc_path.strip()[-3:]=='txt':
      tokenizer = BertTokenizer(voc_path, do_lower_case=True, max_len=512)
    else:
      datasss = torch.load(voc_path)
      tokenizer = datasss['dico']

    # get pron dict for rythm
    vocab_rytm = collections.OrderedDict()
    pron_dict = PronDict('data/raw_pinyin.txt')
    # print (pron_dict['䮘'])
    # print (len(pron_dict))
    for i in range(len(tokenizer)):
        tok = tokenizer.ids_to_tokens[i]
        if tok not in pron_dict:
            vocab_rytm[i] = [0]
        else:
            tok_rhymes=[]
            for pinyin in pron_dict[tok]:
                # print (pinyin[0])
                tok_rhymes.append(get_rhyme(pinyin[0]))
            tok_rhymes=list(set(tok_rhymes))
            vocab_rytm[i] = tok_rhymes
    assert len(vocab_rytm) == len(tokenizer)
    with open(vocab_rytm_file, "w") as w:
        for i in range(len(vocab_rytm)):
            w.write(str(vocab_rytm[i])+'\n')
    tokenizer.ids_to_rytms = vocab_rytm
    
    if txt_path.strip()[-3:]=='txt':
        # split train_valid
        train_sents, valid_sents = split_train_valid(txt_path, 1.1, pron_dict, isjueju)
        bin_path_tr = txt_path.strip()[:-4]
        bin_path_tr += '.pth'
        # process data
        data = get_data(train_sents, tokenizer)
        # saveing data
        print("Saving the data to %s ..." % bin_path_tr)
        torch.save(data, bin_path_tr)
        # display results
        logger.info("%i words (%i unique) in %i sentences." % (
            len(data['sentences']) - len(data['positions']),
            len(data['dico'].vocab),
            len(data['positions'])
        ))
        if len(data['unk_words']) > 0:
            logger.info("%i unknown words (%i unique), covering %.2f%% of the data." % (
                sum(data['unk_words'].values()),
                len(data['unk_words']),
                sum(data['unk_words'].values()) * 100. / (len(data['sentences']) - len(data['positions']))
            ))
            tmp_sort = sorted(data['unk_words'].items(), key=lambda x: x[1])[::-1]
            if len(data['unk_words']) < 30:
                for w, c in tmp_sort:
                    logger.info("%s: %i" % (w, c))
            else:
                tmp_sort = tmp_sort[0:30]
                for w, c in tmp_sort:
                    logger.info("%s: %i" % (w, c))

        else:
            logger.info("0 unknown word.")
    else:
        # split train_valid
        print("Spliting train valid from input...")
        train_sents, valid_sents = split_train_valid(txt_path, 0.75, pron_dict, isjueju)
        # save valid
        with io.open(txt_path+ '.vl.txt', "w", encoding='utf8') as f:
            for line in valid_sents:
                f.write(line+'\n') 
        with io.open(txt_path+ '.tr.txt', "w", encoding='utf8') as f:
            for line in train_sents:
                f.write(line+'\n') 

        # process data
        print("Processing training data...")
        data = get_data(train_sents, tokenizer)
        # saveing data
        print("Saving the data to %s ..." % bin_path_tr)
        torch.save(data, bin_path_tr)
        # display results
        logger.info("%i words (%i unique) in %i sentences." % (
            len(data['sentences']) - len(data['positions']),
            len(data['dico'].vocab),
            len(data['positions'])
        ))
        if len(data['unk_words']) > 0:
            logger.info("%i unknown words (%i unique), covering %.2f%% of the data." % (
                sum(data['unk_words'].values()),
                len(data['unk_words']),
                sum(data['unk_words'].values()) * 100. / (len(data['sentences']) - len(data['positions']))
            ))
            tmp_sort = sorted(data['unk_words'].items(), key=lambda x: x[1])[::-1]
            if len(data['unk_words']) < 30:
                for w, c in tmp_sort:
                    logger.info("%s: %i" % (w, c))
            else:
                tmp_sort = tmp_sort[0:30]
                for w, c in tmp_sort:
                    logger.info("%s: %i" % (w, c))

        else:
            logger.info("0 unknown word.")


        # process data
        print("Processing valid data...")
        data = get_data(valid_sents, tokenizer)
        # saveing data
        print("Saving the data to %s ..." % bin_path_vl)
        torch.save(data, bin_path_vl)
        # display results
        logger.info("%i words (%i unique) in %i sentences." % (
            len(data['sentences']) - len(data['positions']),
            len(data['dico'].vocab),
            len(data['positions'])
        ))
        if len(data['unk_words']) > 0:
            logger.info("%i unknown words (%i unique), covering %.2f%% of the data." % (
                sum(data['unk_words'].values()),
                len(data['unk_words']),
                sum(data['unk_words'].values()) * 100. / (len(data['sentences']) - len(data['positions']))
            ))
            tmp_sort = sorted(data['unk_words'].items(), key=lambda x: x[1])[::-1]
            if len(data['unk_words']) < 30:
                for w, c in tmp_sort:
                    logger.info("%s: %i" % (w, c))
            else:
                tmp_sort = tmp_sort[0:30]
                for w, c in tmp_sort:
                    logger.info("%s: %i" % (w, c))
        else:
            logger.info("0 unknown word.")