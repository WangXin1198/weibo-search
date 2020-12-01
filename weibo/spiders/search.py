# -*- coding: utf-8 -*-
import os
import re
import sys
import json
from datetime import datetime, timedelta
from urllib.parse import unquote

import scrapy
import weibo.utils.util as util
from scrapy.exceptions import CloseSpider
from scrapy.utils.project import get_project_settings
from weibo.items import WeiboItem, CommentItem


from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

import time
from tqdm import tqdm

class SearchSpider(scrapy.Spider):
    name = 'search'
    allowed_domains = ['weibo.com']
    settings = get_project_settings()
    keyword_list = settings.get('KEYWORD_LIST')
    if not isinstance(keyword_list, list):
        if not os.path.isabs(keyword_list):
            keyword_list = os.getcwd() + os.sep + keyword_list
        if not os.path.isfile(keyword_list):
            print('不存在%s文件' % keyword_list)
            sys.exit()
        keyword_list = util.get_keyword_list(keyword_list)

    for i, keyword in enumerate(keyword_list):
        if len(keyword) > 2 and keyword[0] == '#' and keyword[-1] == '#':
            keyword_list[i] = '%23' + keyword[1:-1] + '%23'
    weibo_type = util.convert_weibo_type(settings.get('WEIBO_TYPE'))
    contain_type = util.convert_contain_type(settings.get('CONTAIN_TYPE'))
    regions = util.get_regions(settings.get('REGION'))
    base_url = 'https://s.weibo.com'
    start_date = settings.get('START_DATE',
                              datetime.now().strftime('%Y-%m-%d'))
    end_date = settings.get('END_DATE', datetime.now().strftime('%Y-%m-%d'))

    login_cookies=util.load_cookies('./cookies/cookies.json')
    mongo_error = False
    pymongo_error = False
    mysql_error = False
    pymysql_error = False

    #self.cookies
    # cookies=[]
    # DEFAULT_REQUEST_HEADERS=settings.get('DEFAULT_REQUEST_HEADERS')
    # for name_value in DEFAULT_REQUEST_HEADERS['cookie'].split(' '):
    #     name,value=name_value.split('=')
    #     cookies.append({'name':name,'value':value})
    # print(cookies)

    def start_requests(self):
        start_date = datetime.strptime(self.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(self.end_date,
                                     '%Y-%m-%d') + timedelta(days=1)
        start_str = start_date.strftime('%Y-%m-%d') + '-0'
        end_str = end_date.strftime('%Y-%m-%d') + '-0'
        for keyword in self.keyword_list:
            if not self.settings.get('REGION') or '全部' in self.settings.get(
                    'REGION'):
                base_url = 'https://s.weibo.com/weibo?q=%s' % keyword
                url = base_url + self.weibo_type
                url += self.contain_type
                url += '&timescope=custom:{}:{}'.format(start_str, end_str)
                yield scrapy.Request(url=url,
                                     callback=self.parse,
                                     meta={
                                         'base_url': base_url,
                                         'keyword': keyword,
                                         'url': url
                                     })
            else:
                for region in self.regions.values():
                    base_url = (
                        'https://s.weibo.com/weibo?q={}&region=custom:{}:1000'
                    ).format(keyword, region['code'])
                    url = base_url + self.weibo_type
                    url += self.contain_type
                    url += '&timescope=custom:{}:{}'.format(start_str, end_str)
                    # 获取一个省的搜索结果
                    yield scrapy.Request(url=url,
                                         callback=self.parse,
                                         meta={
                                             'base_url': base_url,
                                             'keyword': keyword,
                                             'province': region,
                                             'url': url
                                         })

    def check_environment(self):
        """判断配置要求的软件是否已安装"""
        if self.pymongo_error:
            print('系统中可能没有安装pymongo库，请先运行 pip install pymongo ，再运行程序')
            raise CloseSpider()
        if self.mongo_error:
            print('系统中可能没有安装或启动MongoDB数据库，请先根据系统环境安装或启动MongoDB，再运行程序')
            raise CloseSpider()
        if self.pymysql_error:
            print('系统中可能没有安装pymysql库，请先运行 pip install pymysql ，再运行程序')
            raise CloseSpider()
        if self.mysql_error:
            print('系统中可能没有安装或正确配置MySQL数据库，请先根据系统环境安装或配置MySQL，再运行程序')
            raise CloseSpider()

    def parse(self, response):
        base_url = response.meta.get('base_url')
        keyword = response.meta.get('keyword')
        province = response.meta.get('province')
        url = response.meta.get('url')
        is_empty = response.xpath(
            '//div[@class="card card-no-result s-pt20b40"]')
        page_count = len(response.xpath('//ul[@class="s-scroll"]/li'))
        if is_empty:
            print('当前页面搜索结果为空')
        elif page_count < 50:
            # 解析当前页面
            for weibo in self.parse_weibo(response):
                self.check_environment()
                yield weibo
            next_url = response.xpath(
                '//a[@class="next"]/@href').extract_first()
            if next_url:
                next_url = self.base_url + next_url
                yield scrapy.Request(url=next_url,
                                     callback=self.parse_page,
                                     meta={'keyword': keyword})
        else:
            start_date = datetime.strptime(self.start_date, '%Y-%m-%d')
            end_date = datetime.strptime(self.end_date, '%Y-%m-%d')
            while start_date <= end_date:
                start_str = start_date.strftime('%Y-%m-%d') + '-0'
                start_date = start_date + timedelta(days=1)
                end_str = start_date.strftime('%Y-%m-%d') + '-0'
                url = base_url + self.weibo_type
                url += self.contain_type
                url += '&timescope=custom:{}:{}&page=1'.format(
                    start_str, end_str)
                # 获取一天的搜索结果
                yield scrapy.Request(url=url,
                                     callback=self.parse_by_day,
                                     meta={
                                         'base_url': base_url,
                                         'keyword': keyword,
                                         'province': province,
                                         'date': start_str[:-2]
                                     })

    def parse_by_day(self, response):
        """以天为单位筛选"""
        base_url = response.meta.get('base_url')
        keyword = response.meta.get('keyword')
        province = response.meta.get('province')
        is_empty = response.xpath(
            '//div[@class="card card-no-result s-pt20b40"]')
        date = response.meta.get('date')
        page_count = len(response.xpath('//ul[@class="s-scroll"]/li'))
        if is_empty:
            print('当前页面搜索结果为空')
        elif page_count < 50:
            # 解析当前页面
            for weibo in self.parse_weibo(response):
                self.check_environment()
                yield weibo
            next_url = response.xpath(
                '//a[@class="next"]/@href').extract_first()
            if next_url:
                next_url = self.base_url + next_url
                yield scrapy.Request(url=next_url,
                                     callback=self.parse_page,
                                     meta={'keyword': keyword})
        else:
            start_date_str = date + '-0'
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d-%H')
            for i in range(1, 25):
                start_str = start_date.strftime('%Y-%m-%d-X%H').replace(
                    'X0', 'X').replace('X', '')
                start_date = start_date + timedelta(hours=1)
                end_str = start_date.strftime('%Y-%m-%d-X%H').replace(
                    'X0', 'X').replace('X', '')
                url = base_url + self.weibo_type
                url += self.contain_type
                url += '&timescope=custom:{}:{}&page=1'.format(
                    start_str, end_str)
                # 获取一小时的搜索结果
                yield scrapy.Request(url=url,
                                     callback=self.parse_by_hour_province
                                     if province else self.parse_by_hour,
                                     meta={
                                         'base_url': base_url,
                                         'keyword': keyword,
                                         'province': province,
                                         'start_time': start_str,
                                         'end_time': end_str
                                     })

    def parse_by_hour(self, response):
        """以小时为单位筛选"""
        keyword = response.meta.get('keyword')
        is_empty = response.xpath(
            '//div[@class="card card-no-result s-pt20b40"]')
        start_time = response.meta.get('start_time')
        end_time = response.meta.get('end_time')
        page_count = len(response.xpath('//ul[@class="s-scroll"]/li'))
        if is_empty:
            print('当前页面搜索结果为空')
        elif page_count < 50:
            # 解析当前页面
            for weibo in self.parse_weibo(response):
                self.check_environment()
                yield weibo
            next_url = response.xpath(
                '//a[@class="next"]/@href').extract_first()
            if next_url:
                next_url = self.base_url + next_url
                yield scrapy.Request(url=next_url,
                                     callback=self.parse_page,
                                     meta={'keyword': keyword})
        else:
            for region in self.regions.values():
                url = ('https://s.weibo.com/weibo?q={}&region=custom:{}:1000'
                       ).format(keyword, region['code'])
                url += self.weibo_type
                url += self.contain_type
                url += '&timescope=custom:{}:{}&page=1'.format(
                    start_time, end_time)
                # 获取一小时一个省的搜索结果
                yield scrapy.Request(url=url,
                                     callback=self.parse_by_hour_province,
                                     meta={
                                         'keyword': keyword,
                                         'start_time': start_time,
                                         'end_time': end_time,
                                         'province': region
                                     })

    def parse_by_hour_province(self, response):
        """以小时和直辖市/省为单位筛选"""
        keyword = response.meta.get('keyword')
        is_empty = response.xpath(
            '//div[@class="card card-no-result s-pt20b40"]')
        start_time = response.meta.get('start_time')
        end_time = response.meta.get('end_time')
        province = response.meta.get('province')
        page_count = len(response.xpath('//ul[@class="s-scroll"]/li'))
        if is_empty:
            print('当前页面搜索结果为空')
        elif page_count < 50:
            # 解析当前页面
            for weibo in self.parse_weibo(response):
                self.check_environment()
                yield weibo
            next_url = response.xpath(
                '//a[@class="next"]/@href').extract_first()
            if next_url:
                next_url = self.base_url + next_url
                yield scrapy.Request(url=next_url,
                                     callback=self.parse_page,
                                     meta={'keyword': keyword})
        else:
            for city in province['city'].values():
                url = ('https://s.weibo.com/weibo?q={}&region=custom:{}:{}'
                       ).format(keyword, province['code'], city)
                url += self.weibo_type
                url += self.contain_type
                url += '&timescope=custom:{}:{}&page=1'.format(
                    start_time, end_time)
                # 获取一小时一个城市的搜索结果
                yield scrapy.Request(url=url,
                                     callback=self.parse_page,
                                     meta={
                                         'keyword': keyword,
                                         'start_time': start_time,
                                         'end_time': end_time,
                                         'province': province,
                                         'city': city
                                     })

    def parse_page(self, response):
        """解析一页搜索结果的信息"""
        keyword = response.meta.get('keyword')
        is_empty = response.xpath(
            '//div[@class="card card-no-result s-pt20b40"]')
        if is_empty:
            print('当前页面搜索结果为空')
        else:
            for weibo in self.parse_weibo(response):
                self.check_environment()
                yield weibo
            next_url = response.xpath(
                '//a[@class="next"]/@href').extract_first()
            if next_url:
                next_url = self.base_url + next_url
                yield scrapy.Request(url=next_url,
                                     callback=self.parse_page,
                                     meta={'keyword': keyword})

    def get_article_url(self, selector):
        """获取微博头条文章url"""
        article_url = ''
        text = selector.xpath('string(.)').extract_first().replace(
            '\u200b', '').replace('\ue627', '').replace('\n',
                                                        '').replace(' ', '')
        if text.startswith('发布了头条文章'):
            urls = selector.xpath('.//a')
            for url in urls:
                if url.xpath(
                        'i[@class="wbicon"]/text()').extract_first() == 'O':
                    if url.xpath('@href').extract_first() and url.xpath(
                            '@href').extract_first().startswith('http://t.cn'):
                        article_url = url.xpath('@href').extract_first()
                    break
        return article_url

    def get_location(self, selector):
        """获取微博发布位置"""
        a_list = selector.xpath('.//a')
        location = ''
        for a in a_list:
            if a.xpath('./i[@class="wbicon"]') and a.xpath(
                    './i[@class="wbicon"]/text()').extract_first() == '2':
                location = a.xpath('string(.)').extract_first()[1:]
                break
        return location

    def get_at_users(self, selector):
        """获取微博中@的用户昵称"""
        a_list = selector.xpath('.//a')
        at_users = ''
        at_list = []
        for a in a_list:
            if len(unquote(a.xpath('@href').extract_first())) > 14 and len(
                    a.xpath('string(.)').extract_first()) > 1:
                if unquote(a.xpath('@href').extract_first())[14:] == a.xpath(
                        'string(.)').extract_first()[1:]:
                    at_user = a.xpath('string(.)').extract_first()[1:]
                    if at_user not in at_list:
                        at_list.append(at_user)
        if at_list:
            at_users = ','.join(at_list)
        return at_users

    def get_topics(self, selector):
        """获取参与的微博话题"""
        a_list = selector.xpath('.//a')
        topics = ''
        topic_list = []
        for a in a_list:
            text = a.xpath('string(.)').extract_first()
            if len(text) > 2 and text[0] == '#' and text[-1] == '#':
                if text[1:-1] not in topic_list:
                    topic_list.append(text[1:-1])
        if topic_list:
            topics = ','.join(topic_list)
        return topics

    def parse_weibo(self, response):
        """解析网页中的微博信息"""
        keyword = response.meta.get('keyword')
        for sel in response.xpath("//div[@class='card-wrap']"):
            info = sel.xpath(
                "div[@class='card']/div[@class='card-feed']/div[@class='content']/div[@class='info']"
            )
            if info:
                weibo = WeiboItem()
                weibo['id'] = sel.xpath('@mid').extract_first()
                weibo['bid'] = sel.xpath(
                    '(.//p[@class="from"])[last()]/a[1]/@href').extract_first(
                ).split('/')[-1].split('?')[0]
                weibo['user_id'] = info[0].xpath(
                    'div[2]/a/@href').extract_first().split('?')[0].split(
                        '/')[-1]
                weibo['screen_name'] = info[0].xpath(
                    'div[2]/a/@nick-name').extract_first()

                # 用户类别
                user_type=info[0].xpath('div[2]/a[2]/@title').extract_first()
                if not user_type:
                    weibo['user_type'] ="其他"
                else:
                    weibo['user_type'] =user_type

                txt_sel = sel.xpath('.//p[@class="txt"]')[0]
                retweet_sel = sel.xpath('.//div[@class="card-comment"]')
                retweet_txt_sel = ''
                if retweet_sel and retweet_sel[0].xpath('.//p[@class="txt"]'):
                    retweet_txt_sel = retweet_sel[0].xpath(
                        './/p[@class="txt"]')[0]
                content_full = sel.xpath(
                    './/p[@node-type="feed_list_content_full"]')
                is_long_weibo = False
                is_long_retweet = False
                if content_full:
                    if not retweet_sel:
                        txt_sel = content_full[0]
                        is_long_weibo = True
                    elif len(content_full) == 2:
                        txt_sel = content_full[0]
                        retweet_txt_sel = content_full[1]
                        is_long_weibo = True
                        is_long_retweet = True
                    elif retweet_sel[0].xpath(
                            './/p[@node-type="feed_list_content_full"]'):
                        retweet_txt_sel = retweet_sel[0].xpath(
                            './/p[@node-type="feed_list_content_full"]')[0]
                        is_long_retweet = True
                    else:
                        txt_sel = content_full[0]
                        is_long_weibo = True
                weibo['text'] = txt_sel.xpath(
                    'string(.)').extract_first().replace('\u200b', '').replace(
                        '\ue627', '')
                weibo['article_url'] = self.get_article_url(txt_sel)
                weibo['location'] = self.get_location(txt_sel)
                if weibo['location']:
                    weibo['text'] = weibo['text'].replace(
                        '2' + weibo['location'], '')
                weibo['text'] = weibo['text'][2:].replace(' ', '')
                if is_long_weibo:
                    weibo['text'] = weibo['text'][:-6]
                weibo['at_users'] = self.get_at_users(txt_sel)
                weibo['topics'] = self.get_topics(txt_sel)
                reposts_count = sel.xpath(
                    './/a[@action-type="feed_list_forward"]/text()'
                ).extract_first()
                try:
                    reposts_count = re.findall(r'\d+.*', reposts_count)
                except TypeError:
                    print('cookie无效或已过期，请按照'
                          'https://github.com/dataabc/weibo-search#如何获取cookie'
                          ' 获取cookie')
                    raise CloseSpider()
                weibo['reposts_count'] = reposts_count[
                    0] if reposts_count else '0'
                comments_count = sel.xpath(
                    './/a[@action-type="feed_list_comment"]/text()'
                ).extract_first()
                comments_count = re.findall(r'\d+.*', comments_count)
                weibo['comments_count'] = comments_count[
                    0] if comments_count else '0'

                #Crawl Comments
                if '万' in weibo['comments_count'] or int(weibo['comments_count'])>20:
                    #详细微博的url
                    comment_url='https://weibo.com/'+weibo['user_id']+'/'+weibo['bid']
                    yield scrapy.Request(url=comment_url,
                                        callback=self.parse_comments,
                                        meta={
                                            'weibo_id': weibo['id'],
                                            'weibo_bid':weibo['bid'],
                                            'weibo_user_id':weibo['user_id'],
                                            'keyword': keyword
                                            })
                                    

                attitudes_count = sel.xpath(
                    '(.//a[@action-type="feed_list_like"])[last()]/em/text()'
                ).extract_first()
                weibo['attitudes_count'] = (attitudes_count
                                            if attitudes_count else '0')
                created_at = sel.xpath(
                    '(.//p[@class="from"])[last()]/a[1]/text()').extract_first(
                ).replace(' ', '').replace('\n', '').split('前')[0]
                weibo['created_at'] = util.standardize_date(created_at)
                source = sel.xpath('(.//p[@class="from"])[last()]/a[2]/text()'
                                   ).extract_first()
                weibo['source'] = source if source else ''
                pics = ''
                is_exist_pic = sel.xpath(
                    './/div[@class="media media-piclist"]')
                if is_exist_pic:
                    pics = is_exist_pic[0].xpath('ul[1]/li/img/@src').extract()
                    pics = [pic[2:] for pic in pics]
                    pics = [
                        re.sub(r'/.*?/', '/large/', pic, 1) for pic in pics
                    ]
                    pics = ['http://' + pic for pic in pics]
                video_url = ''
                is_exist_video = sel.xpath(
                    './/div[@class="thumbnail"]/a/@action-data')
                if is_exist_video:
                    video_url = is_exist_video.extract_first()
                    video_url = unquote(
                        str(video_url)).split('video_src=//')[-1]
                    video_url = 'http://' + video_url
                if not retweet_sel:
                    weibo['pics'] = pics
                    weibo['video_url'] = video_url
                else:
                    weibo['pics'] = ''
                    weibo['video_url'] = ''
                weibo['retweet_id'] = ''
                if retweet_sel and retweet_sel[0].xpath(
                        './/div[@node-type="feed_list_forwardContent"]/a[1]'):
                    retweet = WeiboItem()
                    retweet['id'] = retweet_sel[0].xpath(
                        './/a[@action-type="feed_list_like"]/@action-data'
                    ).extract_first()[4:]
                    retweet['bid'] = retweet_sel[0].xpath(
                        './/p[@class="from"]/a/@href').extract_first().split(
                            '/')[-1].split('?')[0]
                    info = retweet_sel[0].xpath(
                        './/div[@node-type="feed_list_forwardContent"]/a[1]'
                    )[0]
                    retweet['user_id'] = info.xpath(
                        '@href').extract_first().split('/')[-1]
                    retweet['screen_name'] = info.xpath(
                        '@nick-name').extract_first()
                    # 转发微博的用户类别
                    user_type=info.xpath('..//a[2]/@title').extract_first()
                    if not user_type:
                        retweet['user_type'] ="其他"
                    else:
                        retweet['user_type'] =user_type
                    retweet['text'] = retweet_txt_sel.xpath(
                        'string(.)').extract_first().replace('\u200b',
                                                             '').replace(
                                                                 '\ue627', '')
                    retweet['article_url'] = self.get_article_url(
                        retweet_txt_sel)
                    retweet['location'] = self.get_location(retweet_txt_sel)
                    if retweet['location']:
                        retweet['text'] = retweet['text'].replace(
                            '2' + retweet['location'], '')
                    retweet['text'] = retweet['text'][2:].replace(' ', '')
                    if is_long_retweet:
                        retweet['text'] = retweet['text'][:-6]
                    retweet['at_users'] = self.get_at_users(retweet_txt_sel)
                    retweet['topics'] = self.get_topics(retweet_txt_sel)
                    reposts_count = retweet_sel[0].xpath(
                        './/ul[@class="act s-fr"]/li/a[1]/text()'
                    ).extract_first()
                    reposts_count = re.findall(r'\d+.*', reposts_count)
                    retweet['reposts_count'] = reposts_count[
                        0] if reposts_count else '0'
                    comments_count = retweet_sel[0].xpath(
                        './/ul[@class="act s-fr"]/li[2]/a[1]/text()'
                    ).extract_first()
                    comments_count = re.findall(r'\d+.*', comments_count)
                    retweet['comments_count'] = comments_count[
                        0] if comments_count else '0'

                    #Crawl Comments
                    if '万' in retweet['comments_count'] or int(retweet['comments_count'])>20:
                        #详细微博的url
                        comment_url='https://weibo.com/'+retweet['user_id']+'/'+retweet['bid']
                        yield scrapy.Request(url=comment_url,
                                            callback=self.parse_comments,
                                            meta={
                                                'weibo_id': retweet['id'],
                                                'weibo_bid':retweet['bid'],
                                                'weibo_user_id':retweet['user_id'],
                                                'keyword': keyword
                                                })           

                    attitudes_count = retweet_sel[0].xpath(
                        './/a[@action-type="feed_list_like"]/em/text()'
                    ).extract_first()
                    retweet['attitudes_count'] = (attitudes_count
                                                  if attitudes_count else '0')
                    created_at = retweet_sel[0].xpath(
                        './/p[@class="from"]/a[1]/text()').extract_first(
                    ).replace(' ', '').replace('\n', '').split('前')[0]
                    retweet['created_at'] = util.standardize_date(created_at)
                    source = retweet_sel[0].xpath(
                        './/p[@class="from"]/a[2]/text()').extract_first()
                    retweet['source'] = source if source else ''
                    retweet['pics'] = pics
                    retweet['video_url'] = video_url
                    retweet['retweet_id'] = ''
                    yield {'weibo': retweet, 'keyword': keyword}
                    weibo['retweet_id'] = retweet['id']
                # print(weibo)
                yield {'weibo': weibo, 'keyword': keyword}

    def parse_comments(self,response):
        MAX_COMM_NUM=10000
        WAIT_TIME=1

        weibo_id=response.meta.get('weibo_id')
        weibo_bid=response.meta.get('weibo_bid')
        weibo_user_id=response.meta.get('weibo_user_id')
        keyword=response.meta.get('keyword')

        '''chrome options'''
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 使用无头谷歌浏览器模式
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('log-level=2') #log级别设为error
        #通知设置，否则浏览器会弹出通知框
        prefs = {
            'profile.default_content_setting_values':{
                'notifications':2
            },
            "profile.managed_default_content_settings.image": 2,

        }        
        chrome_options.add_experimental_option('prefs',prefs)
        driver = webdriver.Chrome(
            chrome_options=chrome_options, executable_path='E:\研三\weibo_crawl\chromedriver_win32/chromedriver.exe')

        # 隐性等待1s
        # driver.implicitly_wait(1)

        #cookie
        try:
            driver.get(response.url)
            time.sleep(WAIT_TIME)
            if driver.current_url!=response.url:
                driver.delete_all_cookies()
                for cookie in self.login_cookies:
                    driver.add_cookie(cookie)
                driver.get(response.url)
                time.sleep(WAIT_TIME)
        except:
            pass

        #按热度排序
        try:
            WebDriverWait(driver, 3, 0.5).until(
                            EC.visibility_of_element_located((By.XPATH, '//div[@node-type="feed_cate"]/ul[@class="clearfix"]//a[@suda-uatrack="key=comment&value=hotcomm"]')))   
            hotcomm=driver.find_element_by_xpath('//div[@node-type="feed_cate"]/ul[@class="clearfix"]//a[@suda-uatrack="key=comment&value=hotcomm"]')  
            hotcomm.click()
            time.sleep(WAIT_TIME)
        except:
            pass       

        try:
            '''滚动到最后一条评论，循环滚动三次'''
            js4 = "arguments[0].scrollIntoView();" 
            WebDriverWait(driver, 3, 0.5).until(
                EC.visibility_of_element_located((By.XPATH, '//div[@class="list_box"]/div[@class="list_ul"]/div[last()]')))

            cur_last_comment=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div[last()]')
            driver.execute_script(js4, cur_last_comment) 
            time.sleep(WAIT_TIME)
            cur_last_comment=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div[last()]')
            driver.execute_script(js4, cur_last_comment) 
            time.sleep(WAIT_TIME)
            cur_last_comment=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div[last()]')
            driver.execute_script(js4, cur_last_comment) 
            time.sleep(WAIT_TIME)

            #定位加载更多元素
            WebDriverWait(driver, 3, 0.5).until(
                EC.visibility_of_element_located((By.XPATH, '//div[@class="list_box"]/div[@class="list_ul"]/a[@action-type="click_more_comment"]')))
            more_comment_ele=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/a[@action-type="click_more_comment"]')

            #点击加载更多，最多点击1000次
            for _ in range(1000):
                more_comment_ele.click()
                time.sleep(WAIT_TIME)
                
                cur_last_comment=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div[last()]')
                cur_last_comment=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div[last()]')
                driver.execute_script(js4, cur_last_comment) 
                time.sleep(WAIT_TIME)

                cur_last_comment=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div[last()]')
                cur_last_comment=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div[last()]')
                driver.execute_script(js4, cur_last_comment)    
                time.sleep(WAIT_TIME)             

                WebDriverWait(driver, 3, 0.5).until(
                    EC.visibility_of_element_located((By.XPATH, '//div[@class="list_box"]/div[@class="list_ul"]/a[@action-type="click_more_comment"]')))
                more_comment_ele=driver.find_element_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/a[@action-type="click_more_comment"]')
        except:
            pass

        #获取评论列表
        try:
            time.sleep(WAIT_TIME)
            comments=driver.find_elements_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div')
            comments=driver.find_elements_by_xpath('//div[@class="list_box"]/div[@class="list_ul"]/div')
            total_num=len(comments)
        except:
            driver.quit()
            return

        #解析每条评论
        crawled_cnt=0
        for comm_no in range(1,total_num+1):
            comment_item=CommentItem()
            comment_item['weibo_id']=weibo_id
            comment_item['weibo_bid']=weibo_bid
            comment_item['weibo_user_id']=weibo_user_id

            xpath='//div[@class="list_box"]/div[@class="list_ul"]/div[{0}]'.format(comm_no)
            ele=driver.find_element_by_xpath(xpath)
            try:
                comment_item['id']=ele.get_attribute('comment_id')
            except:
                print('comment id test!')

            try:
                WB_text=ele.find_element_by_xpath('./div[@class="list_con"]/div[@class="WB_text"]')
            except:
                continue

            comment_item['user_id']=WB_text.find_element_by_xpath('./a[1]').get_attribute('href').split('/')[-1]
            comment_item['screen_name']=WB_text.find_element_by_xpath('./a[1]').text

            #user_type
            user_type=[]
            try:
                title=WB_text.find_element_by_xpath('./a[@suda-data]/i').get_attribute('title')
                user_type.append(title)
            except:
                pass

            try:
                type=WB_text.find_element_by_xpath('./a[@action-type]').get_attribute('title')
                user_type.append(type)
            except:
                pass
            if not user_type:
                user_type='其他'
            else:
                user_type=';'.join(user_type)
            comment_item['user_type']=user_type

            #attitudes_count
            comment_item['attitudes_count']=0
            try:
                like_count=ele.find_element_by_xpath('.//ul[@class="clearfix"]/li//span[@node-type="like_status"]/em[last()]').text
                if like_count!='赞':
                    comment_item['attitudes_count']=like_count
            except:
                pass
                
            #text
            comment_item['text']=WB_text.text

            #created at
            try:
                created_at=ele.find_element_by_xpath('./div[@class="list_con"]/div[@class="WB_func clearfix"]/div[@class="WB_from S_txt2"]').text.replace(' ', '').replace('\n', '').split('前')[0]
                comment_item['created_at'] = created_at
            except:
                comment_item['created_at']='None'

            yield {'comment': comment_item,'keyword': keyword}
            crawled_cnt+=1
            if crawled_cnt>MAX_COMM_NUM:
                break
               
        driver.quit()
        return 




