---
name: scheset
description: >-
  Plan tomorrow's schedule by integrating classroom timetables, long-term plans, and real-time user input. 
  Use this skill when the user needs to generate a structured schedule file (sche_{date}.json) for calendar synchronization.
---

# Schedule Planner (scheset)

## 1. Information Sources (L3)
- **Static Curriculum**: `references/classtable.json` (Weekly recurring classes).
- **Long-term Context**: `references/longtermsche.md` (Key milestones and deadlines).
- **Real-time Input**: Prompt via WeChat channel to the primary contact.

## 2. Execution Workflow
1. **Date Anchoring**: 
   - Identify today's date (Current Time).
   - Calculate **tomorrow's** date ($YYYY-MM-DD$) and its weekday.
2. **Channel Inquiry**:
   - MUST send WeChat message: "正在规划明天的日程，请问您明天有什么特别的计划吗？"
   - Capture user's reply for task extraction.
3. **Data Integration & Formatting**:
   - **From `classtable.json`**: Extract lessons for tomorrow. Set `"type": "课程"` and `"color": "red"`.
   - **From `longtermsche.md`**: Scan for matching dates. Set `"type": "任务"` and `"color": "normal"`.
   - **From WeChat**: Parse time and task. Set `"type": "任务"` and `"color": "normal"`.
4. **Conflict Resolution**:
   - Retain both items if a class overlaps with a task.
   - For multiple long-term items on the same day, ensure they are listed as separate entries without overwriting.
5. **Serialization**:
   - Sort all events chronologically by `time_start`.
   - Write the JSON object strictly to `workspace/sche_{date}.json`.
6. **Active Trigger (CRITICAL)**:
   - **Immediately after the file is saved, you MUST explicitly state: "Schedule file generated. Now invoking `gogskill` to sync with calendar."**
   - Proceed to call `gogskill` with the newly created file path.

## 3. Anti-Patterns
- **NO SILENCE**: Do not stop after saving the file. You must proceed to the `gogskill` step.
- **NO GUESSING**: If WeChat reply is missing, proceed with available file data.
- **STRICT COLORING**: ONLY classes from `classtable.json` are marked "red".

## 4. Output Schema (sche_{date}.json)
```json
{
  "date": "YYYY-MM-DD",
  "source_integrity": {
    "wechat_input": true,
    "longterm_check": true
  },
  "events": [
    {
      "time_start": "HH:mm",
      "time_end": "HH:mm",
      "title": "String",
      "type": "课程 | 任务",
      "location": "String (optional)",
      "description": "String",
      "color": "normal | red"
    }
  ]
}