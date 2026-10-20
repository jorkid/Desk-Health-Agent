import json

def load_knowledge_base(path: str) -> list:
    """读 knowledge_base.json，返回条目列表。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_search_text(item: dict) -> str:
    """拼出要 embedding 的"检索坐标"文本。
    把：部位 + 部位别名 + 所有症状的标签，全部拼在一起。
    这样用户问"眼干""腰累""肩酸"都能命中。
    """
    parts = [item["部位"]]
    parts.extend(item.get("部位别名", []))
    # 把每个症状的标签都加进来
    for symptom in item.get("症状", []):
        parts.extend(symptom.get("标签", []))
    # 保序去重 + 用空格连起来
    return " ".join(dict.fromkeys(parts))

def build_payload(item: dict) -> dict:
    """命中后要取回喂给 LLM 的载荷。
    直接把业务字段原样返回，不加id这种内部字段。
    """
    return {
        "部位": item["部位"],
        "鉴别问题": item["鉴别问题"],
        "症状": item["症状"],
        "严重程度判定": item["严重程度判定"],
        "分级建议": item["分级建议"],
        "预防建议": item["预防建议"],
    }