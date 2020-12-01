'''
Author: Wang Xin
Date: 2020-11-23 16:10:20
LastEditTime: 2020-11-27 17:43:03
Description: file content
'''
from scrapy import cmdline
# cmdline.execute('scrapy crawl search -s JOBDIR=checkpoint/search_test'.split())
cmdline.execute('scrapy crawl search'.split())
