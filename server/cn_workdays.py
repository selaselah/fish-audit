"""Reproduce a contractual reference to the State Council's 2026 mainland work schedule."""

from datetime import timedelta


SOURCE_KEY = "mainland-workdays-2026"
SOURCE = {
    "title":"《国务院办公厅关于2026年部分节假日安排的通知》",
    "edition":"国办发明电〔2025〕7号",
    "url":"https://www.gov.cn/gongbao/2025/issue_12406/material/gwygb202532.pdf",
    "locator":"元旦至国庆节七项放假及调休安排",
    "scope":"适用于明确采用全国调休安排的 2026 年工作日条款。企业自定日历及银行营业日另核。",
    "summary":"在通常周一至周五的基础上按通知逐日标记放假和调休上班日。",
}
HOLIDAYS = ((1,1,3),(2,15,23),(4,4,6),(5,1,5),(6,19,21),(9,25,27),(10,1,7))
EXTRA_WORK = {(1,4),(2,14),(2,28),(5,9),(9,20),(10,10)}


def working_date(day):
    if day.year!=2026:
        return None
    if (day.month,day.day) in EXTRA_WORK:
        return "调休上班",True
    if any(day.month==month and first<=day.day<=last for month,first,last in HOLIDAYS):
        return "放假",False
    return ("工作日",True) if day.weekday()<5 else ("周末",False)


def after_workdays(start,count):
    if start.year!=2026 or count<=0:
        return None,[]
    current=start
    trace=[]
    counted=0
    while counted<count:
        current+=timedelta(days=1)
        item=working_date(current)
        if item is None:
            return None,trace
        kind,working=item
        counted+=int(working)
        trace.append({"date":current.isoformat(),"kind":kind,"counted":working,"total":counted})
    return current,trace
