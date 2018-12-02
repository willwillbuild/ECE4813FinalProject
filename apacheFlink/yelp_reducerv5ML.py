################################################################################
#  Licensed to the Apache Software Foundation (ASF) under one
#  or more contributor license agreements.  See the NOTICE file
#  distributed with this work for additional information
#  regarding copyright ownership.  The ASF licenses this file
#  to you under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance
#  with the License.  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
# limitations under the License.
################################################################################
import sys

from flink.plan.Environment import get_environment
from flink.functions.FlatMapFunction import FlatMapFunction
from flink.functions.GroupReduceFunction import GroupReduceFunction
import json
import datetime



# review_count,fans,time,compliment_sum,votes_sum,avg_review_length,avg_consistency,avg_useful,total_useful
weights = [1] * 9
elites = [102, 4, 100, 10, 40, 73.14, 1, 0.0018, 1]
decision = []
learningRate = 0.1

user_file = "yelp_academic_dataset_user.json"
business_file = "yelp_academic_dataset_business.json"
review_file = "yelp_academic_dataset_review.json"
output_file = "elite.csv"

class ReviewMapper(FlatMapFunction):
    def flat_map(self,value,collector):
        dict = json.loads(value)
        collector.collect((dict['user_id'],dict['business_id'],dict['length'],dict['stars'],dict['useful'],1))

class BusinessMapper(FlatMapFunction):
    def flat_map(self,value,collector):
        dict = json.loads(value)
        collector.collect((dict['business_id'],dict['stars']))

class UserMapper(FlatMapFunction):
    def flat_map(self,value,collector):
        dict = json.loads(value)
        compliment_sum = dict['compliment_hot']+dict['compliment_cool']+dict['compliment_more']+dict['compliment_list']+dict['compliment_cute']+dict['compliment_note']+dict['compliment_funny']+dict['compliment_plain']+dict['compliment_photos']+dict['compliment_profile']+dict['compliment_writer']
        votes_sum = dict['useful']+dict['funny']+dict['cool']
        time = ((datetime.datetime.now() - datetime.datetime.strptime(dict['yelping_since'],"%Y-%m-%d")).days) /30
        elite = False
        if "2018" in dict['elite']:
            elite = True
        collector.collect((dict['user_id'],dict['review_count'],dict['fans'],elite,time,compliment_sum,votes_sum))

class ReviewReducer(GroupReduceFunction):
    def reduce(self,iterator,collector):
        total_review_length = 0
        total_consistency = 0
        total_useful = 0

        for x in iterator:
            total_review_length += x[2]
            total_consistency += x[3] - x[6]
            total_useful += x[4]

        collector.collect((x[0],total_review_length,total_consistency,total_useful))

class FinalReducer(GroupReduceFunction):
    def reduce (self,iterator,collector):
        for x in iterator:
            avg_review_length = float(x[7]) / x[1]
            avg_consistency = float(x[8]) / x[1]
            avg_useful = float(x[9]) / x[1]

        # user_id,review_count,fans,elite,time,compliment_sum,votes_sum,avg_review_length,avg_consistency,avg_useful,total_useful
        collector.collect((x[0],x[1],x[2],x[3],x[4],x[5],x[6],avg_review_length,avg_consistency,avg_useful,x[9]))

class MLReducer(GroupReduceFunction):
    def reduce(self,iterator,collector):
        it = iterator.next()
        user_id = it[0]
        avg_useful = it[9]
        total_useful = it[10]
        review_count = it[1]
        fans = it[2]
        avg_review_length = it[7]
        avg_consistency = it[8]
        compliment_sum = it[5]
        votes_sum = it[6]
        time = it[4]
        elite = it[3]
        indVect = [avg_useful, total_useful, review_count, fans, avg_review_length, avg_consistency, compliment_sum, votes_sum, time, elite]
        eliteSum = 0
        notEliteSum = 0
        for ind, indicator,eliteVal,weightVal in zip(range(9), indVect,elites,weights):
            indicator = float(indicator)
            if indicator > eliteVal:
                eliteSum += weightVal
            else:
                notEliteSum += weightVal
            if (int(elite) == 1 and indicator < eliteVal) or (int(elite) == 0 and indicator > eliteVal):
                    weights[ind] *= 1 - learningRate

        collector.collect((user_id, 1 if eliteSum > notEliteSum else 0,weights))


if __name__ == "__main__":
    env = get_environment()

    review_data = env.read_text(review_file)
    business_data = env.read_text(business_file)
    user_data = env.read_text(user_file)

    pre_review = review_data \
        .flat_map(ReviewMapper())
    business = business_data \
        .flat_map(BusinessMapper())

    review = pre_review.join(business) \
        .where(1) \
        .equal_to(0) \
        .project_first(0,1,2,3,4,5).project_second(1) \
        .group_by(0) \
        .reduce_group(ReviewReducer(),combinable=True) \

    pre_user = user_data \
        .flat_map(UserMapper()) \

    user = pre_user.join(review) \
        .where(0) \
        .equal_to(0) \
        .project_first(0,1,2,3,4,5,6).project_second(1,2,3) \
        .group_by(0) \
        .reduce_group(FinalReducer(),combinable=True) \

    decision = user \
        .group_by(0) \
        .reduce_group(MLReducer(),combinable=True) \
        .write_csv(output_file,write_mode=1)


    env.set_parallelism(1)

    env.execute(local=True)
