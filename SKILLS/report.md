---
name: report_generator
description: 매출 보고서를 조회·생성하고 이메일로 발송하는 멀티스텝 작업
trigger: ["보고서", "리포트", "report", "이메일 발송", "주간 매출", "일일 매출"]
priority: 8
requires_tools: ["fetch_sales", "render_report", "send_email"]
---

# 보고서 자동 생성 가이드

## 절차
1. `add_todo` 로 아래 3단계를 한 번에 등록한다.
2. `fetch_sales(date_from, date_to)` 로 원천 데이터 조회 후 `complete_todo`.
3. `render_report(template, data)` 로 본문 생성 후 `complete_todo`.
4. `send_email(to, subject, body)` 로 발송 후 `complete_todo`.

## 필수 슬롯
- 보고 기간: 사용자가 "오늘 / 어제 / 이번 주" 등 명시하지 않으면 한 번에 하나씩 되묻는다.
- 수신자: 명시하지 않으면 "기본 그룹으로 보낼까요, 특정 인원에게 보낼까요?" 라고 보기를 제시한다.

## 금지
- 임의의 이메일 주소나 수신자 그룹을 추측하지 않는다.
- 데이터 조회 범위를 사용자가 지정한 기간 밖으로 확장하지 않는다.
- 데이터가 비어 있을 때 임의의 더미 값을 채워 넣지 않는다.
