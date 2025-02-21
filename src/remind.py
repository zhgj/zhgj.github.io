#!/usr/bin/python3
# -*- coding: utf-8 -*-
import sys
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
from time_nlp.TimeNormalizer import TimeNormalizer
from append_remind import *

def main():
    # 检查参数个数
    if len(sys.argv) < 2:
        param = input(u"格式：什么时间 提醒我 干什么事\n")
    else:
        # 获取参数
        param = sys.argv[1]

    remind_keyword = u"提醒"
    if remind_keyword not in param:
        print(u"不是提醒语句")
        return
    tn = TimeNormalizer()

    # remind = u"明天上午9点半提醒我植物"
    remind = param
    remind_list = remind.replace(u"我",u"").split(remind_keyword)
    remind_list = [item for item in remind_list if item]
    if len(remind_list) != 2:
        print(u"提醒语句不完整")
        return
    remind_time_desc = remind_list[0]
    remind_text = remind_list[1]

    res = tn.parse(target=remind_time_desc.replace(u"后", u"")) # target为待分析语句，timeBase为基准时间默认是当前时间
    print(res)
    json_obj = json.loads(res)
    if u"error" in json_obj:
        print(u"时间解析出现错误，换种说法？")
        return
    if json_obj["type"] == "timestamp":
        remind_time = json_obj["timestamp"] # 字符串转时间 datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    elif json_obj["type"] == "timedelta":
        timedelta_obj = json_obj["timedelta"]
        timespan = relativedelta(
            years=timedelta_obj["year"],
            months=timedelta_obj["month"],
            days=timedelta_obj["day"], 
            hours=timedelta_obj["hour"], 
            minutes=timedelta_obj["minute"], 
            seconds=timedelta_obj["second"])
        current_time = datetime.now()
        remind_time = (current_time + timespan).strftime("%Y-%m-%d %H:%M:%S") # 时间格式化为字符串
    elif json_obj["type"] == "timespan":
        print(u"是时间区间，取开始时间")
        timespan_list = json_obj["timespan"]
        remind_time = timespan_list[0]
    else:
        print(u"未知的时间类型")
        return

    print(remind_time)
    print(remind_text)

    # 获取当前文件的 sha 和 content
    sha_and_content = get_file_sha_and_content()
    if sha_and_content is None:
        return
    sha = sha_and_content[0]
    content = sha_and_content[1]
    if not sha or not content:
        return
    print(content)

    # 在文件末尾添加新的一行
    # new_line = u"提醒6,这是第六条提醒,2025-01-18 01:15:00,未发送\r\n"
    new_line = '{0},{1},{2},{3}'.format(remind_text, remind_text, remind_time, u"未发送\n")
    new_content = content + new_line
    print(new_content)

    # 更新文件
    update_file_content(new_content, sha)

if __name__ == '__main__':
    main()