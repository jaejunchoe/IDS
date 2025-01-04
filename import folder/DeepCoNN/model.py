# -*- coding: utf-8 -*-
"""model.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1xX_ZE_mkNTp4zsL5u1YY0LAc_pWSu6yN
"""

import torch
from torch import nn


# User와 item 리뷰에서 feature 추출하는 역할
class CNN(nn.Module):
    def __init__(self, config, word_dim):
        super(CNN, self).__init__()
        self.kernel_count = config.kernel_count
        self.review_count = config.review_count

        self.conv = nn.Sequential(
            nn.Conv1d(in_channels=word_dim, out_channels=config.kernel_count, kernel_size=config.kernel_size, padding=(config.kernel_size - 1) // 2),  # # out shape(new_batch_size, kernel_count, review_length)
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(1, config.review_length)), #  # out shape(new_batch_size,kernel_count,1)
            nn.Dropout(p=config.dropout_prob))

        self.linear = nn.Sequential(
            nn.Linear(config.kernel_count * config.review_count, config.cnn_out_dim),
            nn.ReLU(),
            nn.Dropout(p=config.dropout_prob))

    # latent 생성하는 함수
    def forward(self, vec):     # input shape(new_batch_size, review_length, word2vec_dim)
        latent = self.conv(vec.permute(0, 2, 1))        # out(new_batch_size, kernel_count, 1)
        latent = self.linear(latent.reshape(-1, self.kernel_count * self.review_count))
        return latent                                       # # out shape(batch_size, cnn_out_dim)

# 추출된 feature로 상호작용(interaction)해서 최종 예측 rating을 생성
class FactorizationMachine(nn.Module):
    def __init__(self, p, k):                               # latent matrix / # p=cnn_out_dim, 입력 벡터의 차원, k = 잠재 차원
        super().__init__()
        self.v = nn.Parameter(torch.rand(p, k) / 10)        # 초기화를 해당 식으로 할당
        self.linear = nn.Linear(p, 1, bias=True)            # 1 = 출력 크기
        self.dropout = nn.Dropout(0.5)

    # latent 생성하는 함수
    def forward(self, x):
        linear_part = self.linear(x)                        # 선형관계 모델링
                                                            # input shape(batch_size, cnn_out_dim), out shape(batch_size, 1)

        inter_part1 = torch.mm(x, self.v) ** 2              # 모든 특징간의 합성곱 -> 입력 데이터 x와 latent matrix(self.v)
        inter_part2 = torch.mm(x ** 2, self.v ** 2)         # 개별 특징의 제곱으로 행렬 곱 전개 -> x^2와 v^2

        # inter_part1은 전체 효과 / inter_part2는 개별 효과의 합산 -> 이 둘을 빼면? = 전체 효과에서 개별 효과를 뺀 값
        # 여기에서 뺀 값의 의미 = 개별 효과로 설명되지 않는 부분 -> 상호작용 효과
        pair_interactions = torch.sum(inter_part1 - inter_part2, dim=1, keepdim=True)       # 값의 차이로 상호작용 추출 + 값 변환
        pair_interactions = self.dropout(pair_interactions)
        return linear_part + 0.5 * pair_interactions                        # = out shape = (batch_size, 1)




# 전체 모델 구조 정의 + CNN과 FactorizationMachine(FM) 결합해서 예측
class DeepCoNN(nn.Module):
    def __init__(self, config, word_emb):
        super(DeepCoNN, self).__init__()
        self.embedding = nn.Embedding.from_pretrained(torch.Tensor(word_emb))
        self.cnn_u = CNN(config, word_dim=self.embedding.embedding_dim)             # user 리뷰 처리
        self.cnn_i = CNN(config, word_dim=self.embedding.embedding_dim)             # item 리뷰 처리
        self.fm = FactorizationMachine(config.cnn_out_dim * 2, 10)                  # latent로 최종 rating 예측

    # 사용자 리뷰(user_review)와 아이템 리뷰(item_review)를 입력받아 처리하는 함수
    # input shape(batch_size, review_count, review_length)
    def forward(self, user_review, item_review):

        # 리뷰 데이터를 배치(batch) 단위로 평탄화(reshape)하여 임베딩에 적합하도록 변환
        new_batch_size = user_review.shape[0] * user_review.shape[1]
        user_review = user_review.reshape(new_batch_size, -1)
        item_review = item_review.reshape(new_batch_size, -1)

        # 임베딩 벡터 변환
        u_vec = self.embedding(user_review)
        i_vec = self.embedding(item_review)

        user_latent = self.cnn_u(u_vec)
        item_latent = self.cnn_i(i_vec)

        concat_latent = torch.cat((user_latent, item_latent), dim=1)        # latent 결합
        return self.fm(concat_latent)                                       # = prediction