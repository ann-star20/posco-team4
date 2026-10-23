"""TCAD 검증 경로 ERD (모델 서비스 -> Gateway -> TCAD 서비스)를 팀 ERD.svg(Mermaid neo 스타일)와 같은 모양의 SVG로 그린다.
  python make_tcad_erd.py   ->  TCAD_검증경로_ERD.svg
"""
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
FONT = '"Recursive Variable","Malgun Gothic","Apple SD Gothic Neo",arial,sans-serif'
INK = "#28253D"
MUTED = "#6B6880"
W, ROW, HEAD = 360, 28, 46

PINK = ("#E879F9", "#FDF4FF")      # 모델 서비스
VIOLET = ("#A78BFA", "#F5F3FF")    # Gateway
TEAL = ("#2DD4BF", "#F0FDFA")      # TCAD 서비스
YELLOW = ("#FACC15", "#FEFCE8")    # 신규 제안 표시

# (이름, 색, 위치, 부제, [(타입, 컬럼, 키, 신규여부)])
ENT = {
    "model": ("diagnose 응답", PINK, (40, 90), "모델 서비스 (JSON, 저장 안 함)", [
        ("uuid", "request_id", "", 0), ("uuid", "job_id", "", 0), ("text", "status", "", 0), ("boolean", "anomaly_detected", "", 0),
        ("text", "decision.top_category", "", 0), ("float", "decision.top_probability", "", 0), ("text", "compensation.route", "", 0),
        ("boolean", "compensation.high_confidence", "", 0), ("jsonb", "compensation.confidence_blockers", "", 0), ("jsonb", "compensation.thresholds", "", 0),
        ("jsonb", "compensation.target_process_parameters", "", 0), ("jsonb", "tcad_proposal", "", 0)]),
    "diag": ("diagnosis_results", VIOLET, (580, 90), "Gateway DB", [
        ("uuid", "job_id", "PK", 0), ("uuid", "source_event_id", "FK", 0), ("text", "top_category", "", 0), ("text", "compensation_route", "", 0),
        ("text", "routing_status", "", 0), ("uuid", "proposal_id", "FK", 0), ("uuid", "tcad_proposal_group_id", "FK", 0)]),
    "group": ("tcad_proposal_groups", VIOLET, (580, 400), "Gateway DB", [
        ("uuid", "proposal_id", "PK", 0), ("uuid", "diagnosis_job_id", "FK", 0), ("uuid", "run_id", "FK", 0), ("uuid", "original_request_id", "", 0),
        ("jsonb", "routing_snapshot", "", 0), ("int", "candidate_count", "", 0), ("int", "terminal_count", "", 0), ("text", "status", "", 0),
        ("uuid", "selected_tcad_request_id", "", 0), ("text", "approved_by", "", 0)]),
    "cand": ("tcad_verification_candidates", VIOLET, (1120, 400), "Gateway DB", [
        ("uuid", "tcad_request_id", "PK", 0), ("uuid", "proposal_id", "FK", 0), ("int", "candidate_index", "", 0), ("jsonb", "process_parameters", "", 0),
        ("jsonb", "predicted_outputs", "", 0), ("jsonb", "result_payload", "", 0), ("jsonb", "spec_verdict", "", 0), ("text", "status", "", 0)]),
    "job": ("tcad_service_jobs", TEAL, (1660, 400), "TCAD 서비스 (상태/작업목록.json)", [
        ("uuid", "request_id", "PK", 0), ("uuid", "job_id", "", 0), ("uuid", "run_id", "", 0), ("text", "status", "", 0), ("text", "progress_stage", "", 0),
        ("jsonb", "process_parameters", "", 0), ("jsonb", "requested_outputs", "", 0), ("jsonb", "predicted_outputs", "", 0), ("jsonb", "result_payload", "", 0),
        ("jsonb", "prediction_error", "", 0), ("text", "error_code", "", 0), ("text", "calc_mode", "", 1), ("timestamptz", "accepted_at", "", 0),
        ("timestamptz", "started_at", "", 0), ("timestamptz", "finished_at", "", 0)]),
}


def height(key):
    return HEAD + ROW * len(ENT[key][4])


def box(key):
    return ENT[key][2][0], ENT[key][2][1], W, height(key)


def entity_svg(key):
    name, (stroke, fill), (x, y), sub, rows = ENT[key]
    h = height(key)
    o = [f'<g><rect x="{x}" y="{y}" width="{W}" height="{h}" rx="10" fill="#ffffff" stroke="{stroke}" stroke-width="2"/>',
         f'<path d="M{x},{y + HEAD} L{x},{y + 10} Q{x},{y} {x + 10},{y} L{x + W - 10},{y} Q{x + W},{y} {x + W},{y + 10} L{x + W},{y + HEAD} Z" fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
         f'<text x="{x + W / 2}" y="{y + 21}" text-anchor="middle" font-weight="700" font-size="15" fill="{INK}">{escape(name)}</text>',
         f'<text x="{x + W / 2}" y="{y + 38}" text-anchor="middle" font-size="11" fill="{MUTED}">{escape(sub)}</text>']
    for i, (t, c, k, new) in enumerate(rows):
        ry = y + HEAD + i * ROW
        if i % 2 == 1:
            o.append(f'<rect x="{x + 1}" y="{ry}" width="{W - 2}" height="{ROW}" fill="{fill}" opacity="0.55"/>')
        if new:
            o.append(f'<rect x="{x + 1}" y="{ry}" width="{W - 2}" height="{ROW}" fill="{YELLOW[1]}" stroke="{YELLOW[0]}" stroke-width="1.5"/>')
        cy = ry + ROW / 2 + 4
        o.append(f'<text x="{x + 12}" y="{cy}" font-size="12" fill="{MUTED}">{escape(t)}</text>')
        o.append(f'<text x="{x + 96}" y="{cy}" font-size="13" font-weight="{600 if k == "PK" else 400}" fill="{INK}">{escape(c)}</text>')
        if k:
            o.append(f'<text x="{x + W - 12}" y="{cy}" text-anchor="end" font-size="11" font-weight="700" fill="{stroke}">{k}</text>')
        if new:
            o.append(f'<text x="{x + W - 12}" y="{cy}" text-anchor="end" font-size="11" font-weight="700" fill="#A16207">신규 제안</text>')
    o.append("</g>")
    return "\n".join(o)


def one(x, y, dx, dy):
    """'1' 기호: 끝점에서 14px 안쪽에 직선 두 개."""
    px, py = -dy, dx
    out = []
    for off in (12, 18):
        cx, cy = x + dx * off, y + dy * off
        out.append(f'<line x1="{cx - px * 8}" y1="{cy - py * 8}" x2="{cx + px * 8}" y2="{cy + py * 8}" stroke="{INK}" stroke-width="2"/>')
    return "".join(out)


def zero_one(x, y, dx, dy):
    px, py = -dy, dx
    cx, cy = x + dx * 12, y + dy * 12
    c = f'<line x1="{cx - px * 8}" y1="{cy - py * 8}" x2="{cx + px * 8}" y2="{cy + py * 8}" stroke="{INK}" stroke-width="2"/>'
    return c + f'<circle cx="{x + dx * 26}" cy="{y + dy * 26}" r="6" fill="#ffffff" stroke="{INK}" stroke-width="2"/>'


def many(x, y, dx, dy):
    """까마귀발: 엔티티 가장자리의 한 점에서 퍼지는 세 선."""
    px, py = -dy, dx
    bx, by = x + dx * 18, y + dy * 18
    return "".join(f'<line x1="{bx}" y1="{by}" x2="{x + px * s * 9}" y2="{y + py * s * 9}" stroke="{INK}" stroke-width="2"/>' for s in (-1, 0, 1)) + \
        f'<line x1="{x + dx * 24}" y1="{y + dy * 24 - 0}" x2="{x + dx * 24}" y2="{y + dy * 24}" stroke="{INK}"/>'


def label(x, y, text, w=None):
    w = w or (len(text) * 7.4 + 20)
    return (f'<rect x="{x - w / 2}" y="{y - 12}" width="{w}" height="22" rx="4" fill="#ffffff" opacity="0.92"/>'
            f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="12" fill="{INK}">{escape(text)}</text>')


def edge_h(a, b, ay_frac, by_frac, left_sym, right_sym, text, dashed=False):
    ax, ay, aw, ah = box(a)
    bx, by, bw, bh = box(b)
    x1, y1 = ax + aw, ay + ah * ay_frac
    x2, y2 = bx, by + bh * by_frac
    mid = (x1 + x2) / 2
    dash = ' stroke-dasharray="8 5"' if dashed else ""
    p = f'<path d="M{x1},{y1} L{mid},{y1} L{mid},{y2} L{x2},{y2}" fill="none" stroke="{INK}" stroke-width="2"{dash}/>'
    return p + left_sym(x1, y1, 1, 0) + right_sym(x2, y2, -1, 0) + label(mid, (y1 + y2) / 2 - 18 if abs(y1 - y2) < 4 else (y1 + y2) / 2, text)


def edge_v(a, b, ax_frac, bx_frac, top_sym, bottom_sym, text):
    ax, ay, aw, ah = box(a)
    bx, by, bw, bh = box(b)
    x1, y1 = ax + aw * ax_frac, ay + ah
    x2, y2 = bx + bw * bx_frac, by
    mid = (y1 + y2) / 2
    p = f'<path d="M{x1},{y1} L{x1},{mid} L{x2},{mid} L{x2},{y2}" fill="none" stroke="{INK}" stroke-width="2"/>'
    return p + top_sym(x1, y1, 0, 1) + bottom_sym(x2, y2, 0, -1) + label(x1 + 120, mid - 16, text)


def main():
    svg_w, svg_h = 2060, 960
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {svg_w} {svg_h}" role="img" font-family=\'{FONT}\' style="background:#ffffff">',
             "<title>TCAD 검증 경로 데이터 모델</title><desc>모델 서비스 응답이 Gateway 테이블에 저장되고 tcad_verify일 때 TCAD 서비스 작업으로 이어지는 관계</desc>",
             f'<text x="40" y="40" font-size="22" font-weight="700" fill="{INK}">TCAD 검증 경로 데이터 모델</text>',
             f'<text x="40" y="64" font-size="13" fill="{MUTED}">모델 서비스 응답 → Gateway 저장 → (route=tcad_verify) TCAD 서비스 작업 → 규격 판정과 승인</text>']
    # 관계선 (엔티티 아래에 그린다)
    parts.append(edge_h("model", "diag", 0.55, 0.4, one, one, "이벤트로 저장"))
    parts.append(edge_v("diag", "group", 0.3, 0.3, one, zero_one, "tcad_verify 일 때만 생성"))
    parts.append(edge_h("group", "cand", 0.4, 0.4, one, many, "후보 보통 2개"))
    parts.append(edge_h("cand", "job", 0.4, 0.4, one, one, "HTTP verify", dashed=True))
    for k in ENT:
        parts.append(entity_svg(k))
    # 범례
    lx, ly = 40, 640
    parts.append(f'<text x="{lx}" y="{ly}" font-size="14" font-weight="700" fill="{INK}">범례</text>')
    for i, (nm, (st, fl)) in enumerate((("모델 서비스 (Jetson)", PINK), ("Gateway DB", VIOLET), ("TCAD 서비스 (워크스테이션 PC)", TEAL), ("신규 제안 필드", YELLOW))):
        yy = ly + 22 + i * 28
        parts.append(f'<rect x="{lx}" y="{yy - 13}" width="26" height="18" rx="4" fill="{fl}" stroke="{st}" stroke-width="2"/><text x="{lx + 36}" y="{yy + 1}" font-size="13" fill="{INK}">{nm}</text>')
    yy = ly + 22 + 4 * 28
    parts.append(f'<line x1="{lx}" y1="{yy - 4}" x2="{lx + 26}" y2="{yy - 4}" stroke="{INK}" stroke-width="2" stroke-dasharray="8 5"/><text x="{lx + 36}" y="{yy}" font-size="13" fill="{INK}">시스템 경계를 넘는 HTTP 호출</text>')
    parts.append(f'<g font-size="12" fill="{MUTED}"><text x="{lx}" y="{yy + 34}">route=apply 는 TCAD 서비스 작업을 만들지 않는다.</text>'
                 f'<text x="{lx}" y="{yy + 52}">보정값은 compensation.target_process_parameters 로 관리자 승인 큐에 간다.</text>'
                 f'<text x="{lx}" y="{yy + 70}">calc_mode(fake/real)는 가짜 결과를 구분하려는 제안 필드다.</text>'
                 f'<text x="{lx}" y="{yy + 88}">이벤트로 저장: ROS /fab/events 의 diagnosis.completed 가 Gateway 에 저장된다.</text>'
                 f'<text x="{lx}" y="{yy + 106}">HTTP verify: POST /api/v1/tcad/verify, tcad_request_id = request_id 로 같은 작업이다.</text></g>')
    parts.append("</svg>")
    out = HERE / "TCAD_검증경로_ERD.svg"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
