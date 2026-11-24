"""Curated methodological references. Rule applicability is defined separately."""

ACCOUNTING = {"title": "《中华人民共和国会计法》（2024年修正）第十四条",
              "url": "https://kjs.mof.gov.cn/zhengcefabu/202408/t20240812_3941615.htm",
              "scope": "原始凭证审核的一般背景。各项勾稽条件为本系统采购检查程序。"}
PROCUREMENT = {"title": "财政部会计司解读《企业内部控制应用指引第7号——采购业务》",
               "url": "https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm",
               "edition": "2010-06-11", "scope": "企业采购业务内控参考，适用性需结合本单位制度。"}
EVIDENCE = {"title": "《中国注册会计师审计准则第1301号——审计证据》",
            "url": "https://www.cicpa.org.cn/ztzl1/Professional_standards/xxzztx/zyzz/sjzz/202105/P020240412542695263912.pdf",
            "edition": "2022-12-22 修订", "scope": "注册会计师审计的方法参考，用于说明证据评估与追加程序思路。"}
SOURCES = {
    "vat-invoice-code": {"title":"国家税务总局《关于推行通过增值税电子发票系统开具的增值税电子普通发票有关问题的公告》",
        "edition":"国家税务总局公告2015年第84号","url":"https://fgk.chinatax.gov.cn/zcfgk/c100012/c5194596/content.html",
        "locator":"第四条","scope":"传统增值税电子普通发票的代码和号码编制口径，用于企业资料勾稽。",
        "summary":"该票种的十二位代码与八位顺序号码分别编制。比对时同时核对票面记载的代码和号码。"},
    "digital-invoice-number": {"title":"国家税务总局《关于推广应用全面数字化电子发票的公告》",
        "edition":"国家税务总局公告2024年第11号","url":"https://fgk.chinatax.gov.cn/zcfgk/c100012/c5236067/content.html",
        "locator":"第一、三、四条","scope":"数电发票的统一赋号和票面要素。票据真伪另行查验。",
        "summary":"数电发票使用二十位号码。程序保留整串及前导零，依据原页进行全号比较。"},
    "electronic-vouchers": {"title":"财政部、国家档案局《关于规范电子会计凭证报销入账归档的通知》",
        "edition":"财会〔2020〕6号","url":"https://www.mof.gov.cn/zcsjtsgb/gfxwj/202003/t20200323_3583778.htm",
        "locator":"第三条第（三）项","scope":"仅使用外部电子会计凭证报销入账归档时的制度背景。同票比对是企业内部复核线索。",
        "summary":"该条件涉及审签程序及防止电子会计凭证重复入账。是否已实际报销或入账，需查验企业记录。"},
    "installment-tracking": {"title":"《企业内部控制应用指引第7号——采购业务》","edition":"2010-04-15",
        "url":"https://kjs.mof.gov.cn/zhengcefabu/201005/P020230421440664863663.pdf","locator":"付款，第十三及十五条",
        "scope":"采购付款跟踪的方法参考。B08 的去重方式和比较口径由本程序定义。",
        "summary":"结合合同、付款凭证和采购记录跟踪付款，定期核对与供应商的往来。"},
    "voucher": {**ACCOUNTING, "edition": "2024年修正", "locator": "第十四条",
                "summary": "核查原始凭证的准确性和完整性，遇有欠缺可要求补正。"},
    "purchase-records": {**PROCUREMENT, "locator": "第二部分（五）合同、（九）会计控制",
                         "summary": "采购合同、验收和付款环节的记录应能相互核对。"},
    "receipt": {**PROCUREMENT, "locator": "第二部分（七）验收",
                "summary": "对照约定检查收到的物资，记录验收结论并处理异常。"},
    "payment": {**PROCUREMENT, "locator": "第二部分（八）付款",
                "summary": "审核付款申请时应关注合同约定、凭证、审批及预付款项。"},
    "evidence-quality": {**EVIDENCE, "locator": "第三、十、十一及十三条",
                         "summary": "证据的来源、准确性、完整性和与检查目标的关系影响其证明力。"},
    "follow-up": {**EVIDENCE, "locator": "第十五条",
                  "summary": "不同来源的材料相互矛盾或可靠性存疑时，应考虑调整检查或追加程序。"},
}
MAPPING = {"B01":["purchase-records","evidence-quality"],"B02":["payment"],"B03":["payment","follow-up"],
           "B08":["installment-tracking","follow-up"],
           "B04":["payment","voucher"],"B05":["evidence-quality","follow-up"],
           "B06":["payment","follow-up"],"B07":["payment","follow-up"],"E01": ["voucher", "evidence-quality"], "P01": ["purchase-records"], "P02": ["purchase-records"],
           "P03": ["purchase-records"], "I01": ["vat-invoice-code","digital-invoice-number","voucher", "follow-up"], "M01": ["voucher"],
           "C01": ["payment"], "M02": ["purchase-records", "payment"], "D01": ["purchase-records"],
           "A01": ["receipt"], "S01": ["receipt"], "X01": ["follow-up"],
           "T01": ["voucher"], "T02": ["evidence-quality"], "T03": ["voucher"],
           "T04": ["evidence-quality"], "T05": ["evidence-quality"], "I02": ["electronic-vouchers", "voucher", "follow-up"]}


def link_sources(graph):
    used = {node["label"]: node["id"] for node in graph["nodes"] if node["type"] == "control"}
    keys = {key for rule in used for key in MAPPING[rule]}
    for key in sorted(keys):
        source = SOURCES[key]
        graph["nodes"].append({"id": "source/" + key, "type": "method_reference",
                               "label": source["title"], **source})
    for rule, node_id in used.items():
        for key in MAPPING[rule]:
            source_id = "source/" + key
            graph["edges"].append({"from": source_id, "to": node_id, "type": "method_reference", "evidence": [source_id]})
