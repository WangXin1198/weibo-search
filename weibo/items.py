'''
Author: Wang Xin
Date: 2020-11-20 15:03:32
LastEditTime: 2020-11-30 09:44:48
Description: file content
'''
# -*- coding: utf-8 -*-

# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class WeiboItem(scrapy.Item):
    # define the fields for your item here like:
    id = scrapy.Field()
    bid = scrapy.Field()
    user_id = scrapy.Field()
    screen_name = scrapy.Field()
    text = scrapy.Field()
    article_url = scrapy.Field()
    location = scrapy.Field()
    at_users = scrapy.Field()
    topics = scrapy.Field()
    reposts_count = scrapy.Field()  # 转发数
    comments_count = scrapy.Field()  # 评论数
    attitudes_count = scrapy.Field()  # 点赞数
    created_at = scrapy.Field()  # 发布时间
    source = scrapy.Field()
    pics = scrapy.Field()
    video_url = scrapy.Field()
    retweet_id = scrapy.Field()
    # 用户类别：微博官方认证，微博个人认证，会员等，Null表示普通用户
    user_type = scrapy.Field()


class CommentItem(scrapy.Item):
    # define the fields of a comment
    id = scrapy.Field()
    user_id = scrapy.Field()
    screen_name = scrapy.Field()
    user_type = scrapy.Field()
    weibo_id = scrapy.Field()
    weibo_bid = scrapy.Field()
    weibo_user_id = scrapy.Field()
    text = scrapy.Field()
    attitudes_count = scrapy.Field()
    created_at = scrapy.Field()
