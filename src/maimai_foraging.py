#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦觅食（MaiMai Foraging）
==========================

基于麦当劳中国 MCP Server（https://mcp.mcd.cn）的「门店 × 餐品 × 优惠券」交叉查询工具，
实现参赛要求的两条用户交互流程：

  路径 A｜领券后查询（coupon-first）
      用户领取优惠券后，查询附近哪些门店有售该券对应餐品、该券在哪些门店可用。

  路径 B｜指定餐品查询（meal-first）
      用户输入指定餐品名称，查询附近哪些门店有售该餐品，
      并同时检查是否有对应优惠券可领取。

依赖：仅 Python 3.8+ 标准库，无需安装第三方包。

用法示例：
    export MCD_MCP_TOKEN="你的Token"
    python src/maimai_foraging.py nearby --city 北京 --keyword 中关村
    python src/maimai_foraging.py coupon-flow --city 北京 --keyword 中关村 --auto-claim
    python src/maimai_foraging.py meal-flow "巨无霸套餐" --city 北京 --keyword 中关村
    python src/maimai_foraging.py --demo meal-flow "巨无霸套餐" --city 北京 --keyword 中关村
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

MCP_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "maimai-foraging", "version": "1.0.0"}
DEFAULT_MAX_STORES = 10      # 单次任务最多逐店查询的门店数（限流友好）
DEFAULT_INTERVAL = 0.2       # 门店查询间隔（秒），官方限流 600 次/分钟

# 到店自取场景
ORDER_TYPE_EAT_IN = 1        # orderType: 1=到店
BE_TYPE_TAKE_OUT = 1         # beType: 1=到店自取（query-nearby-stores 同义）
BE_TYPE_DRIVE_THRU = 5       # beType: 5=得来速


class UserError(Exception):
    """用户输入或配置问题（缺 Token、缺位置参数等）。"""


class MCPError(Exception):
    """MCP 通信错误或工具业务错误。"""


# ---------------------------------------------------------------------------
# MCP 客户端（Streamable HTTP + JSON-RPC 2.0）
# ---------------------------------------------------------------------------

class MCPClient:
    """麦当劳 MCP Server 的最小客户端：initialize / tools/call。"""

    def __init__(self, url: str = MCP_URL, token: Optional[str] = None, timeout: int = 30):
        if not token:
            raise UserError("缺少 MCP Token：请设置环境变量 MCD_MCP_TOKEN，或使用 --demo 体验演示数据")
        self.url = url
        self.token = token
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self._req_id = 0

    # -- JSON-RPC 基础 ------------------------------------------------------

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _post(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise MCPError("HTTP %s（%s）：%s" % (exc.code, _http_hint(exc.code), detail))
        except urllib.error.URLError as exc:
            raise MCPError("网络错误：%s" % exc.reason)

        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        raw = resp.read().decode("utf-8", "replace")
        ctype = resp.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            return _parse_sse(raw)
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def initialize(self) -> None:
        self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        })
        # initialized 通知（无响应）
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })
        if not isinstance(resp, dict):
            raise MCPError("工具 %s 返回异常：%r" % (name, resp))
        if "error" in resp:
            raise MCPError("工具 %s 调用失败：%s" % (name, resp["error"]))
        result = resp.get("result") or {}
        if result.get("isError"):
            raise MCPError("工具 %s 执行业务错误" % name)
        return result


def _http_hint(code: int) -> str:
    return {401: "Token 无效/过期，请至 https://open.mcd.cn/mcp 重新申请",
            429: "触发限流（600 次/分钟），请稍后重试"}.get(code, "请求失败")


def _parse_sse(raw: str) -> Optional[Dict[str, Any]]:
    """解析 text/event-stream，返回最后一个可解析的 JSON-RPC 消息。"""
    messages = []
    for block in raw.split("\n\n"):
        data_lines = [line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")]
        text = "\n".join(data_lines).strip()
        if not text:
            continue
        try:
            messages.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("jsonrpc"):
            return msg
    return messages[-1] if messages else None


def tool_payload(result: Any) -> Any:
    """把 tools/call 的 result.content 解析为 Python 对象（兼容纯 JSON 与文本）。"""
    if isinstance(result, dict) and "content" in result:
        texts = [c.get("text", "") for c in result.get("content", [])
                 if isinstance(c, dict) and c.get("type") == "text"]
        text = "\n".join(texts).strip()
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return result


# ---------------------------------------------------------------------------
# 防御式数据提取（官方未公开完整响应结构，递归兼容多种字段命名）
# ---------------------------------------------------------------------------

def _norm(s: Any) -> str:
    return re.sub(r"[\s\u3000]+", "", str(s or "")).lower()


def _first(d: Dict[str, Any], keys: Tuple[str, ...], default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
    return default


def _iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _iter_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_dicts(v)


@dataclass
class Store:
    code: str
    be_code: str
    name: str
    address: str = ""
    distance: str = ""


@dataclass
class Meal:
    code: str
    name: str
    price: str = ""
    category: str = ""


@dataclass
class Coupon:
    cid: str
    title: str
    detail: str = ""
    products: List[str] = field(default_factory=list)
    expire: str = ""
    status: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


def extract_stores(data: Any) -> List[Store]:
    out: List[Store] = []
    seen = set()
    for d in _iter_dicts(data):
        if "productCode" in d or "productName" in d:
            continue  # 餐品节点，不是门店
        code = _first(d, ("storeCode", "storeId", "storeNO"))
        name = _first(d, ("storeName", "storeFullName", "name", "title"))
        if not code or not name or code in seen:
            continue
        seen.add(code)
        out.append(Store(
            code=code,
            be_code=_first(d, ("beCode", "be", "beId")),
            name=name,
            address=_first(d, ("address", "storeAddress", "addr", "fullAddress")),
            distance=_first(d, ("distance", "distanceKm", "distanceStr", "dist")),
        ))
    return out


def extract_meals(data: Any) -> List[Meal]:
    out: List[Meal] = []
    seen = set()
    for d in _iter_dicts(data):
        if "storeCode" in d and "productCode" not in d and "productName" not in d:
            continue  # 门店节点，不是餐品
        code = _first(d, ("productCode", "code", "productId", "saleCode"))
        name = _first(d, ("productName", "name", "title", "saleName"))
        if (not code and not name) or (code or name) in seen:
            continue
        seen.add(code or name)
        out.append(Meal(
            code=code,
            name=name,
            price=_first(d, ("price", "currentPrice", "salePrice", "promotionPrice", "originalPrice")),
            category=_first(d, ("category", "categoryName", "typeName", "menuType")),
        ))
    return out


def _coupon_products(d: Dict[str, Any]) -> List[str]:
    prods: List[str] = []
    for k in ("productList", "products", "applyProducts", "scopeProducts",
              "productNames", "bindProducts", "productScope"):
        v = d.get(k)
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    nm = _first(item, ("productName", "name", "title"))
                    cd = _first(item, ("productCode", "code"))
                    if nm or cd:
                        prods.append(nm or cd)
                elif isinstance(item, str) and item.strip():
                    prods.append(item.strip())
    return prods


def extract_coupons(data: Any) -> List[Coupon]:
    out: List[Coupon] = []
    seen = set()
    for d in _iter_dicts(data):
        if "productCode" in d:
            continue
        cid = _first(d, ("couponId", "couponCode", "id"))
        title = _first(d, ("title", "couponName", "couponTitle", "name"))
        if not title or not (cid or _coupon_products(d)):
            continue
        key = (cid, title)
        if key in seen:
            continue
        seen.add(key)
        out.append(Coupon(
            cid=cid,
            title=title,
            detail=_first(d, ("detail", "description", "subTitle", "remark", "content", "discount")),
            products=_coupon_products(d),
            expire=_first(d, ("expireTime", "endTime", "validityEnd", "expireDate",
                              "validEnd", "expire")),
            status=_first(d, ("status", "couponStatus", "state")),
            raw=d,
        ))
    return out


# ---------------------------------------------------------------------------
# 匹配规则
# ---------------------------------------------------------------------------

def meal_hit(meal: Meal, keyword: str) -> bool:
    """餐品匹配：productCode 精确匹配优先，其次名称包含匹配（忽略空格/大小写）。"""
    k = _norm(keyword)
    if not k:
        return False
    if meal.code and k == _norm(meal.code):
        return True
    return bool(meal.name) and k in _norm(meal.name)


def coupon_has_meal(coupon: Coupon, meal_name: str, meal_code: str = "") -> bool:
    """券匹配：适用餐品 productCode/名称命中，或券内任意文本包含餐品名。"""
    mn = _norm(meal_name)
    if mn and len(mn) >= 2:
        for p in coupon.products:
            pn = _norm(p)
            if pn and (pn == mn or pn in mn or mn in pn):
                return True
        if meal_code:
            mc = _norm(meal_code)
            for v in coupon.raw.values():
                if isinstance(v, str) and mc and mc in _norm(v):
                    return True
        for v in coupon.raw.values():
            if isinstance(v, str) and mn in _norm(v):
                return True
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and mn in _norm(item):
                        return True
                    if isinstance(item, dict):
                        for sv in item.values():
                            if isinstance(sv, str) and mn in _norm(sv):
                                return True
    return False


_TITLE_NOISE = re.compile(
    r"(立减\s*\d+(\.\d+)?\s*元?|减\s*\d+(\.\d+)?\s*元?|省\s*\d+(\.\d+)?\s*元?|"
    r"第\s*\d+\s*份\s*半价|第二份半价|买一送一|优惠券|代金券|兑换券|券)")


def guess_products_from_title(title: str) -> List[str]:
    """券名无结构化适用餐品字段时，从券名剥离优惠噪声词得到餐品名候选。"""
    t = _TITLE_NOISE.sub(" ", str(title or ""))
    parts = [p.strip(" ，,。.、;；:：") for p in re.split(r"[/+＋]", t)]
    return [p for p in parts if len(p) >= 2]


# ---------------------------------------------------------------------------
# 位置与门店查询
# ---------------------------------------------------------------------------

@dataclass
class Location:
    city: str = ""
    keyword: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    be_type: int = BE_TYPE_TAKE_OUT

    def store_args(self) -> Dict[str, Any]:
        if self.lat is not None and self.lng is not None:
            return {"searchType": 3, "latitude": self.lat, "longitude": self.lng,
                    "beType": self.be_type}
        if self.city and self.keyword:
            return {"searchType": 2, "city": self.city, "keyword": self.keyword,
                    "beType": self.be_type}
        raise UserError("缺少位置信息：请提供 --city 城市 + --keyword 地点，或 --lat/--lng 经纬度")


def query_nearby_stores(client: Any, loc: Location) -> List[Store]:
    data = tool_payload(client.call_tool("query-nearby-stores", loc.store_args()))
    return extract_stores(data)


def _meal_args(store: Store, order_type: int = ORDER_TYPE_EAT_IN,
               be_type: int = BE_TYPE_TAKE_OUT) -> Dict[str, Any]:
    return {"storeCode": store.code, "beCode": store.be_code,
            "orderType": order_type, "beType": be_type}


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------

def _disp_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _disp_width(s))


def render_table(headers: List[str], rows: List[List[str]]) -> str:
    cols = len(headers)
    widths = [_disp_width(h) for h in headers]
    srows = []
    for r in rows:
        cells = [str(x) for x in r] + [""] * (cols - len(r))
        srows.append(cells)
        for i, c in enumerate(cells):
            widths[i] = max(widths[i], _disp_width(c))
    lines = ["  ".join(_pad(h, widths[i]) for i, h in enumerate(headers)),
             "  ".join("-" * widths[i] for i in range(cols))]
    for cells in srows:
        lines.append("  ".join(_pad(cells[i], widths[i]) for i in range(cols)))
    return "\n".join(lines)


class Report:
    def __init__(self) -> None:
        self.lines: List[str] = []

    def add(self, text: str = "") -> None:
        self.lines.append(text)

    def text(self) -> str:
        return "\n".join(self.lines)


def _brief(data: Any, limit: int = 120) -> str:
    s = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    return (s[:limit] + "…") if len(s) > limit else s


# ---------------------------------------------------------------------------
# 路径 A：领券后查询
# ---------------------------------------------------------------------------

def pick_coupon(coupons: List[Coupon], keyword: Optional[str],
                interactive: bool = True) -> Coupon:
    pool = coupons
    if keyword:
        k = _norm(keyword)
        pool = [c for c in coupons
                if k in _norm(c.title) or any(k in _norm(p) for p in c.products)]
        if not pool:
            raise UserError("已领券中未找到与「%s」匹配的优惠券" % keyword)
    if len(pool) == 1:
        return pool[0]
    if interactive and sys.stdin.isatty():
        print("检测到多张已领优惠券，请选择目标券：")
        for i, c in enumerate(pool, 1):
            scope = "、".join(c.products) if c.products else "（适用餐品见券名）"
            print("  [%d] %s —— 适用：%s" % (i, c.title, scope))
        try:
            idx = int(input("请输入序号：").strip())
            return pool[idx - 1]
        except (ValueError, IndexError, EOFError, KeyboardInterrupt):
            print("输入无效，默认使用第 1 张。")
    return pool[0]


def flow_coupon_first(client: Any, loc: Location, *, auto_claim: bool = False,
                      coupon_keyword: Optional[str] = None,
                      max_stores: int = DEFAULT_MAX_STORES,
                      interval: float = DEFAULT_INTERVAL,
                      interactive: bool = True) -> str:
    """路径 A：领券后查询附近有售该券对应餐品的门店。"""
    rep = Report()
    rep.add("【路径 A · 领券后查询】")

    if auto_claim:
        data = tool_payload(client.call_tool("auto-bind-coupons"))
        rep.add("· 已执行一键领券：%s" % _brief(data))

    my_coupons = extract_coupons(tool_payload(client.call_tool("query-my-coupons")))
    if not my_coupons:
        rep.add("· 未查询到已领取的优惠券。可先执行 auto-bind-coupons 领券，或改用路径 B（指定餐品查询）。")
        return rep.text()

    target = pick_coupon(my_coupons, coupon_keyword, interactive=interactive)
    scope = "、".join(target.products) if target.products else "、".join(
        guess_products_from_title(target.title)) or "（未能解析适用餐品）"
    expire = "，有效期至 %s" % target.expire if target.expire else ""
    rep.add("· 目标优惠券：%s（适用：%s%s）" % (target.title, scope, expire))

    stores = query_nearby_stores(client, loc)
    if not stores:
        rep.add("· 未查询到附近门店，请更换位置关键词后重试。")
        return rep.text()
    stores = stores[:max_stores]
    rep.add("· 附近门店 %d 家，逐一核实餐品在售与门店券可用性…" % len(stores))

    rows, sold_stores, coupon_ok_stores, failed = [], 0, 0, 0
    for i, st in enumerate(stores):
        if i:
            time.sleep(interval)
        try:
            menu = extract_meals(tool_payload(client.call_tool("query-meals", _meal_args(st))))
            store_coupons = extract_coupons(
                tool_payload(client.call_tool("query-store-coupons", _meal_args(st))))
        except MCPError as exc:
            failed += 1
            rows.append([st.name, _store_label(st), "未查询到", "查询失败：%s" % exc])
            continue

        hits = []
        for name in (target.products or guess_products_from_title(target.title)):
            hits.extend(m for m in menu if meal_hit(m, name))
        uniq, seen = [], set()
        for m in hits:
            if m.code and m.code in seen:
                continue
            if m.code:
                seen.add(m.code)
            uniq.append(m)

        if uniq:
            sold_stores += 1
            meal_cell = "；".join(
                "%s%s" % (m.name, (" ¥" + m.price) if m.price else "") for m in uniq)
        else:
            meal_cell = "未查询到在售"

        coupon_ok = any(
            (c.cid and c.cid == target.cid) or _norm(c.title) == _norm(target.title)
            for c in store_coupons)
        if coupon_ok:
            coupon_ok_stores += 1
        coupon_cell = "本店可用" if coupon_ok else "本店券列表未见该券"
        rows.append([st.name, _store_label(st), meal_cell, coupon_cell])

    rep.add("")
    rep.add(render_table(["门店名称", "地址/距离", "餐品在售（价格）", "门店券"], rows))
    rep.add("")
    rep.add("结论：附近 %d/%d 家门店有售「%s」，其中 %d 家门店券列表包含该券%s。" % (
        sold_stores, len(stores), scope.split("、")[0], coupon_ok_stores,
        ("；%d 家查询失败" % failed) if failed else ""))
    rep.add("优惠券明细：%s ｜ %s ｜ %s ｜ 状态：%s ｜ 适用餐品：%s" % (
        target.title, target.detail or "见券名",
        ("有效期至 %s" % target.expire) if target.expire else "有效期见券包",
        target.status or "已拥有", scope))
    rep.add("（价格与供应状态具有时效性，以麦当劳官方渠道实时结果为准）")
    return rep.text()


# ---------------------------------------------------------------------------
# 路径 B：指定餐品查询
# ---------------------------------------------------------------------------

def flow_meal_first(client: Any, loc: Location, meal_name: str, *,
                    max_stores: int = DEFAULT_MAX_STORES,
                    interval: float = DEFAULT_INTERVAL,
                    include_mine: bool = True) -> str:
    """路径 B：查询附近有售指定餐品的门店，并匹配可领取/已拥有的优惠券。"""
    rep = Report()
    rep.add("【路径 B · 指定餐品查询】目标餐品：%s" % meal_name)

    stores = query_nearby_stores(client, loc)
    if not stores:
        rep.add("· 未查询到附近门店，请更换位置关键词后重试。")
        return rep.text()
    stores = stores[:max_stores]
    rep.add("· 附近门店 %d 家，逐一核实餐品在售情况…" % len(stores))

    rows, sold_stores, failed, matched_meals = [], 0, 0, []
    for i, st in enumerate(stores):
        if i:
            time.sleep(interval)
        try:
            menu = extract_meals(tool_payload(client.call_tool("query-meals", _meal_args(st))))
        except MCPError as exc:
            failed += 1
            rows.append([st.name, _store_label(st), "未查询到（%s）" % exc])
            continue
        hits = [m for m in menu if meal_hit(m, meal_name)]
        if hits:
            sold_stores += 1
            matched_meals.extend(hits)
            cell = "；".join("%s%s" % (m.name, (" ¥" + m.price) if m.price else "")
                             for m in hits)
        else:
            cell = "未查询到在售"
        rows.append([st.name, _store_label(st), cell])

    rep.add("")
    rep.add(render_table(["门店名称", "地址/距离", "餐品在售（价格）"], rows))
    rep.add("")

    # 可领取的优惠券
    available = extract_coupons(tool_payload(client.call_tool("available-coupons")))
    can_claim = [c for c in available if coupon_has_meal(c, meal_name)]
    rep.add("可领取的优惠券（麦麦省）：")
    if can_claim:
        for c in can_claim:
            rep.add("  - %s（%s%s）" % (c.title, "、".join(c.products) or c.detail or "见券名",
                                       "，有效期至 %s" % c.expire if c.expire else ""))
    else:
        rep.add("  - 暂未找到与「%s」匹配的可领取优惠券" % meal_name)

    # 已拥有的相关券
    if include_mine:
        mine = extract_coupons(tool_payload(client.call_tool("query-my-coupons")))
        owned = [c for c in mine if coupon_has_meal(c, meal_name)]
        rep.add("你已拥有的相关优惠券：")
        if owned:
            for c in owned:
                rep.add("  - %s（%s）" % (c.title, "有效期至 %s" % c.expire if c.expire else "见券包"))
        else:
            rep.add("  - 卡包中暂无与「%s」匹配的优惠券" % meal_name)

    rep.add("")
    rep.add("结论：附近 %d/%d 家门店有售「%s」；可领券 %d 张%s。" % (
        sold_stores, len(stores), meal_name, len(can_claim),
        ("；%d 家查询失败" % failed) if failed else ""))
    rep.add("（价格与供应状态具有时效性，以麦当劳官方渠道实时结果为准）")
    return rep.text()


def _store_label(st: Store) -> str:
    parts = [p for p in (st.address, st.distance) if p]
    return " · ".join(parts) if parts else "—"


# ---------------------------------------------------------------------------
# 演示数据（--demo，无需 Token）
# ---------------------------------------------------------------------------

DEMO_STORES = [
    {"storeCode": "1450555", "beCode": "145055502", "storeName": "麦当劳(中关村大街店)",
     "address": "北京市海淀区中关村大街1号", "distance": "0.4km"},
    {"storeCode": "1450666", "beCode": "145066602", "storeName": "麦当劳(五道口店)",
     "address": "北京市海淀区成府路28号", "distance": "1.2km"},
    {"storeCode": "1450777", "beCode": "145077702", "storeName": "麦当劳(西直门店)",
     "address": "北京市西城区西直门内大街", "distance": "2.1km"},
]

DEMO_MENUS = {
    "1450555": [
        {"productCode": "9900013701", "productName": "麦辣鸡腿堡套餐", "price": "28.5", "category": "套餐"},
        {"productCode": "9900013702", "productName": "麦辣鸡腿堡", "price": "14.5", "category": "汉堡"},
        {"productCode": "9900013722", "productName": "巨无霸套餐", "price": "32.0", "category": "套餐"},
        {"productCode": "9900013723", "productName": "巨无霸", "price": "17.5", "category": "汉堡"},
        {"productCode": "9900013801", "productName": "薯条(大)", "price": "11.0", "category": "小食"},
    ],
    "1450666": [
        {"productCode": "9900013722", "productName": "巨无霸套餐", "price": "32.0", "category": "套餐"},
        {"productCode": "9900013723", "productName": "巨无霸", "price": "17.5", "category": "汉堡"},
        {"productCode": "9900013751", "productName": "板烧鸡腿堡套餐", "price": "27.0", "category": "套餐"},
        {"productCode": "9900013851", "productName": "麦乐鸡(5块)", "price": "11.0", "category": "小食"},
    ],
    "1450777": [
        {"productCode": "9900013702", "productName": "麦辣鸡腿堡", "price": "14.5", "category": "汉堡"},
        {"productCode": "9900013851", "productName": "麦乐鸡(5块)", "price": "11.0", "category": "小食"},
        {"productCode": "9900013901", "productName": "菠萝派", "price": "6.5", "category": "甜品"},
    ],
}

DEMO_MY_COUPONS = {"coupons": [
    {"couponId": "C20261012001", "title": "麦辣鸡腿堡套餐 立减10元", "detail": "立减10元",
     "productList": [{"productName": "麦辣鸡腿堡套餐", "productCode": "9900013701"}],
     "expireTime": "2026-10-31", "status": "已领取"},
    {"couponId": "C20261012002", "title": "巨无霸套餐 减5元", "detail": "减5元",
     "productList": [{"productName": "巨无霸套餐", "productCode": "9900013722"}],
     "expireTime": "2026-11-05", "status": "已领取"},
]}

DEMO_AVAILABLE_COUPONS = {"coupons": [
    {"couponId": "C20261012901", "title": "巨无霸套餐 第二份半价", "detail": "第二份半价",
     "productList": [{"productName": "巨无霸套餐", "productCode": "9900013722"}],
     "expireTime": "2026-11-10", "status": "可领取"},
    {"couponId": "C20261012902", "title": "麦辣鸡腿堡 立减5元", "detail": "立减5元",
     "productList": [{"productName": "麦辣鸡腿堡", "productCode": "9900013702"}],
     "expireTime": "2026-10-31", "status": "可领取"},
    {"couponId": "C20261012903", "title": "板烧鸡腿堡套餐 减8元", "detail": "减8元",
     "productList": [{"productName": "板烧鸡腿堡套餐", "productCode": "9900013751"}],
     "expireTime": "2026-11-15", "status": "可领取"},
]}

DEMO_STORE_COUPONS = {
    "1450555": {"coupons": [
        {"couponId": "C20261012001", "title": "麦辣鸡腿堡套餐 立减10元", "status": "本店可用"},
        {"couponId": "C20261012901", "title": "巨无霸套餐 第二份半价", "status": "本店可用"},
    ]},
    "1450666": {"coupons": [
        {"couponId": "C20261012901", "title": "巨无霸套餐 第二份半价", "status": "本店可用"},
    ]},
    "1450777": {"coupons": [
        {"couponId": "C20261012902", "title": "麦辣鸡腿堡 立减5元", "status": "本店可用"},
    ]},
}


class DemoClient:
    """内置演示数据客户端：接口与 MCPClient 相同，但不访问网络。"""

    def initialize(self) -> None:
        return None

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments or {}
        if name == "query-nearby-stores":
            data = {"stores": DEMO_STORES}
        elif name == "query-my-coupons":
            data = DEMO_MY_COUPONS
        elif name == "available-coupons":
            data = DEMO_AVAILABLE_COUPONS
        elif name == "auto-bind-coupons":
            data = {"success": True, "claimedCount": 3,
                    "message": "（演示数据）已自动领取 3 张可领优惠券"}
        elif name == "query-meals":
            code = str(args.get("storeCode", ""))
            data = {"meals": DEMO_MENUS.get(code, [])}
        elif name == "query-store-coupons":
            code = str(args.get("storeCode", ""))
            data = DEMO_STORE_COUPONS.get(code, {"coupons": []})
        elif name == "query-meal-detail":
            data = {"detail": "（演示数据）套餐详情"}
        elif name == "now-time-info":
            data = {"currentTime": "2026-10-12 20:00:00（演示数据）"}
        else:
            data = {"message": "（演示数据）工具 %s" % name}
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _add_location_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--city", help="城市，searchType=2 时必填，如：北京")
    p.add_argument("--keyword", help="位置关键词，如：中关村")
    p.add_argument("--lat", type=float, help="纬度（searchType=3，与 --lng 同时使用）")
    p.add_argument("--lng", type=float, help="经度（searchType=3，与 --lat 同时使用）")
    p.add_argument("--be-type", type=int, default=BE_TYPE_TAKE_OUT, choices=[1, 5],
                   help="1=到店自取（默认），5=得来速")


def _add_flow_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--max-stores", type=int, default=DEFAULT_MAX_STORES,
                   help="最多逐店查询的门店数量（默认 %d，限流友好）" % DEFAULT_MAX_STORES)
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                   help="门店查询间隔秒数（默认 %.1f）" % DEFAULT_INTERVAL)
    p.add_argument("--no-interactive", action="store_true",
                   help="多张券时不弹窗选择，直接使用第一张")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maimai_foraging",
        description="麦麦觅食 —— 麦当劳「门店 × 餐品 × 优惠券」交叉查询（路径A：领券后查询；路径B：指定餐品查询）")
    parser.add_argument("--token", default=os.environ.get("MCD_MCP_TOKEN"),
                        help="麦当劳 MCP Token（默认读环境变量 MCD_MCP_TOKEN）")
    parser.add_argument("--url", default=MCP_URL, help="MCP Server 地址")
    parser.add_argument("--demo", action="store_true",
                        help="使用内置演示数据，无需 Token")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_nearby = sub.add_parser("nearby", help="查询附近门店列表")
    _add_location_args(p_nearby)

    p_a = sub.add_parser("coupon-flow", help="路径 A：领券后查询附近有售门店")
    _add_location_args(p_a)
    _add_flow_args(p_a)
    p_a.add_argument("--auto-claim", action="store_true", help="先执行一键领券")
    p_a.add_argument("--coupon", help="指定已领券名称（不指定则自动选择/弹窗选择）")

    p_b = sub.add_parser("meal-flow", help="路径 B：指定餐品查询有售门店与可领券")
    _add_location_args(p_b)
    _add_flow_args(p_b)
    p_b.add_argument("meal", help="目标餐品名称，如：巨无霸套餐")
    return parser


def make_client(args: argparse.Namespace) -> Any:
    if args.demo:
        return DemoClient()
    client = MCPClient(url=args.url, token=args.token)
    client.initialize()
    return client


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = make_client(args)
        loc = Location(city=args.city or "", keyword=args.keyword or "",
                       lat=args.lat, lng=args.lng, be_type=args.be_type)
        if args.cmd == "nearby":
            stores = query_nearby_stores(client, loc)
            if not stores:
                print("未查询到附近门店，请更换位置关键词后重试。")
                return 1
            print("附近门店 %d 家：" % len(stores))
            print(render_table(
                ["门店名称", "地址/距离", "storeCode", "beCode"],
                [[s.name, _store_label(s), s.code, s.be_code] for s in stores]))
        elif args.cmd == "coupon-flow":
            print(flow_coupon_first(
                client, loc, auto_claim=args.auto_claim, coupon_keyword=args.coupon,
                max_stores=args.max_stores, interval=args.interval,
                interactive=not args.no_interactive))
        elif args.cmd == "meal-flow":
            print(flow_meal_first(
                client, loc, args.meal, max_stores=args.max_stores,
                interval=args.interval))
        return 0
    except UserError as exc:
        print("输入/配置问题：%s" % exc, file=sys.stderr)
        return 2
    except MCPError as exc:
        print("MCP 调用失败：%s" % exc, file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
