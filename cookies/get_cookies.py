'''
Author: Wang Xin
Date: 2020-11-27 11:09:44
LastEditTime: 2020-12-01 10:34:43
Description: file content
'''
import selenium
from selenium import webdriver
import json
import time
import pdb

driver = webdriver.Chrome(
    executable_path='E:\研三\weibo_crawl\chromedriver_win32/chromedriver.exe')
driver.implicitly_wait(5)
url = 'https://weibo.com/login.php'
driver.get(url)
driver.maximize_window()
pdb.set_trace()
cookies = driver.get_cookies()
with open('cookies.json', 'w') as fout:
    json.dump(cookies, fout)
driver.close()
