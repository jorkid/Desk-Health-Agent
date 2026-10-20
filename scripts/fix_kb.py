# -*- coding: utf-8 -*-
"""一次性修复知识库：①条目间补逗号 ②长周期自测改为即时自测"""
import json
import re

path = r"d:\Software\project\python\gwjkgj\deskpal\rag\knowledge_base.json"
with open(path, encoding="utf-8") as f:
    text = f.read()

# ① 修复条目间缺逗号：任意 `}` 后跟空白再跟 `{`（无论缩进/空行）都补逗号
fixed = re.sub(r'\}\s*\{', '}, {', text)
data = json.loads(fixed)
print("逗号修复成功，条目数 =", len(data))

# ② 长周期自测 → 即时自测（原长周期干预内容在分级/预防建议中已有对应，直接替换）
fixes = [
    ("fatigue_energy", "持续乏力", "现在起身走动2分钟并深呼吸：乏力稍缓解→久坐循环慢；不缓解→睡眠不足或慢性疲劳"),
    ("fatigue_energy", "脑子累", "闭眼深呼吸2分钟：注意力恢复→精神疲劳；不恢复→长期透支可能"),
    ("sleep_quality", "入睡难", "回想最近一周：是否常躺下超30分钟才入睡→入睡困难；偶尔→偶发"),
    ("sleep_quality", "睡眠浅", "回想最近一周：是否频繁夜醒或多梦→睡眠结构问题；偶尔→环境偶扰"),
    ("sleep_quality", "早醒", "回想最近一周：是否常比预期早醒且难再入睡→早醒问题；偶尔→偶发"),
    ("digestion", "便秘", "现在顺时针揉腹2分钟：出现肠鸣或便意→蠕动可改善；无反应→需饮食调整"),
    ("skin_face", "出油", "清水洗脸后对镜观察：仍明显泛油光→出油多；干爽→偶发"),
    ("skin_face", "暗沉", "对镜观察当前气色：明显暗沉无光泽→循环/睡眠问题；尚可→偶发"),
    ("skin_face", "敏感", "轻按压脸颊：明显泛红刺痛→屏障弱/敏感；无反应→偶发刺激"),
    ("metabolism_weight", "体重涨", "对比3个月前的体重/腰围：明显上升→热量盈余；基本稳定→偶发波动"),
    ("metabolism_weight", "血糖高", "回想最近一次体检：血糖/血脂是否超标→代谢问题；正常→偶发"),
]

changed = 0
for item in data:
    for kf, label, new_self in fixes:
        if item["id"] == kf:
            for sym in item["症状"]:
                if sym["标签"][0] == label:
                    old = sym.get("自测", "")
                    sym["自测"] = new_self
                    print(f"[改] {kf}/{label}: {old}  ->  {new_self}")
                    changed += 1

print("共修改自测", changed, "处")

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("已写回", path)
