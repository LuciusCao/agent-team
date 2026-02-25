---
name: project-manager
description: 项目经理 Agent Skill - 理解项目需求、自动拆分任务、监控进度、协调资源
metadata:
  {
    openclaw: { emoji: "📊", triggers: ["创建项目", "拆分任务", "项目进度", "规划", "breakdown"] },
    zeroclaw: { compatible: true },
  }
---

# Project Manager Skill

项目经理 Agent 专用 Skill，负责：
1. 理解项目需求并创建项目
2. 自动拆分任务（Breakdown）
3. 监控项目进度
4. 协调资源分配

## 触发条件

- "创建项目 xxx"
- "拆分任务"
- "规划项目"
- "项目进度"
- "breakdown"

## 配置

```env
TASK_SERVICE_URL=http://host.docker.internal:8080
AGENT_NAME=project-manager
```

## 工具函数

```python
import os
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta

TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://localhost:8080")
AGENT_NAME = os.getenv("AGENT_NAME", "project-manager")

# ============ 项目管理 ============

def create_project(name: str, description: str, discord_channel_id: str = None) -> Dict:
    """创建新项目"""
    resp = requests.post(
        f"{TASK_SERVICE_URL}/projects",
        json={
            "name": name,
            "description": description,
            "discord_channel_id": discord_channel_id
        }
    )
    resp.raise_for_status()
    return resp.json()

def get_project_progress(project_id: int) -> Dict:
    """获取项目进度"""
    resp = requests.get(f"{TASK_SERVICE_URL}/projects/{project_id}/progress")
    resp.raise_for_status()
    return resp.json()

def get_project_tasks(project_id: int) -> List[Dict]:
    """获取项目所有任务"""
    resp = requests.get(f"{TASK_SERVICE_URL}/projects/{project_id}/tasks")
    return resp.json()

# ============ 任务拆分 ============

def breakdown_project(project_id: int, tasks: List[Dict]) -> Dict:
    """
    项目拆分：批量创建任务
    
    tasks 格式:
    [
        {
            "title": "任务标题",
            "description": "任务描述",
            "task_type": "research|copywrite|video|development|...",
            "priority": 1-10,
            "estimated_hours": 2.5,
            "task_tags": ["frontend", "react"],
            "dependencies": [],  # 依赖的任务索引
            "acceptance_criteria": "验收标准"
        }
    ]
    """
    # 转换依赖关系（从索引转换为实际任务ID）
    resp = requests.post(
        f"{TASK_SERVICE_URL}/projects/{project_id}/breakdown",
        json=tasks
    )
    resp.raise_for_status()
    return resp.json()

def auto_breakdown(project_id: int, project_description: str, project_type: str = "software") -> Dict:
    """
    自动拆分项目 - 基于项目描述生成任务列表
    
    这是模板化的自动拆分，实际应由 LLM 根据描述智能拆分
    """
    templates = {
        "software": [
            {
                "title": "需求分析与架构设计",
                "description": "分析项目需求，设计系统架构",
                "task_type": "analysis",
                "priority": 10,
                "estimated_hours": 4,
                "task_tags": ["analysis", "architecture"],
                "dependencies": [],
                "acceptance_criteria": "- 输出需求文档\n- 完成架构设计图"
            },
            {
                "title": "项目初始化",
                "description": "创建项目基础结构，配置开发环境",
                "task_type": "development",
                "priority": 9,
                "estimated_hours": 2,
                "task_tags": ["setup", "development"],
                "dependencies": [],
                "acceptance_criteria": "- 项目能正常启动\n- 基础配置完成"
            },
            {
                "title": "核心功能开发",
                "description": "实现核心业务逻辑",
                "task_type": "development",
                "priority": 8,
                "estimated_hours": 8,
                "task_tags": ["development", "core"],
                "dependencies": [0, 1],  # 依赖前两个任务
                "acceptance_criteria": "- 核心功能正常工作\n- 单元测试通过"
            },
            {
                "title": "UI/UX 开发",
                "description": "实现用户界面",
                "task_type": "design",
                "priority": 7,
                "estimated_hours": 6,
                "task_tags": ["frontend", "ui", "design"],
                "dependencies": [1],
                "acceptance_criteria": "- 界面美观\n- 响应式布局"
            },
            {
                "title": "集成测试",
                "description": "端到端测试",
                "task_type": "testing",
                "priority": 6,
                "estimated_hours": 4,
                "task_tags": ["testing", "qa"],
                "dependencies": [2, 3],
                "acceptance_criteria": "- 所有测试用例通过\n- 无严重bug"
            },
            {
                "title": "文档编写",
                "description": "编写项目文档",
                "task_type": "copywrite",
                "priority": 5,
                "estimated_hours": 3,
                "task_tags": ["documentation"],
                "dependencies": [],
                "acceptance_criteria": "- README 完整\n- API 文档清晰"
            },
            {
                "title": "部署上线",
                "description": "部署到生产环境",
                "task_type": "deployment",
                "priority": 8,
                "estimated_hours": 2,
                "task_tags": ["deployment", "devops"],
                "dependencies": [4, 5],
                "acceptance_criteria": "- 生产环境可访问\n- 监控配置完成"
            }
        ],
        "content": [
            {
                "title": "内容策划",
                "description": "确定内容主题和结构",
                "task_type": "analysis",
                "priority": 10,
                "estimated_hours": 2,
                "task_tags": ["planning"],
                "dependencies": [],
                "acceptance_criteria": "- 主题明确\n- 大纲完整"
            },
            {
                "title": "资料收集",
                "description": "收集相关资料和数据",
                "task_type": "research",
                "priority": 9,
                "estimated_hours": 4,
                "task_tags": ["research"],
                "dependencies": [0],
                "acceptance_criteria": "- 资料充分\n- 数据准确"
            },
            {
                "title": "内容撰写",
                "description": "撰写主要内容",
                "task_type": "copywrite",
                "priority": 8,
                "estimated_hours": 6,
                "task_tags": ["writing"],
                "dependencies": [1],
                "acceptance_criteria": "- 内容完整\n- 逻辑清晰"
            },
            {
                "title": "视觉设计",
                "description": "设计配图和排版",
                "task_type": "design",
                "priority": 7,
                "estimated_hours": 4,
                "task_tags": ["design", "visual"],
                "dependencies": [0],
                "acceptance_criteria": "- 配图精美\n- 排版美观"
            },
            {
                "title": "内容审核",
                "description": "审核内容质量",
                "task_type": "review",
                "priority": 8,
                "estimated_hours": 2,
                "task_tags": ["review"],
                "dependencies": [2, 3],
                "acceptance_criteria": "- 无错误\n- 质量达标"
            },
            {
                "title": "发布推广",
                "description": "发布内容并推广",
                "task_type": "publish",
                "priority": 7,
                "estimated_hours": 2,
                "task_tags": ["publish", "marketing"],
                "dependencies": [4],
                "acceptance_criteria": "- 成功发布\n- 推广到位"
            }
        ]
    }
    
    template = templates.get(project_type, templates["software"])
    
    return breakdown_project(project_id, template)

# ============ 资源协调 ============

def get_available_agents(skill: str = None) -> List[Dict]:
    """获取可用 Agent"""
    params = {"status": "online"}
    if skill:
        params["skill"] = skill
    
    resp = requests.get(f"{TASK_SERVICE_URL}/agents", params=params)
    return resp.json()

def recommend_assignee(task_tags: List[str]) -> Optional[Dict]:
    """
    根据任务标签推荐合适的 Agent
    简单实现：找技能匹配度最高的 online Agent
    """
    agents = get_available_agents()
    
    best_match = None
    best_score = 0
    
    for agent in agents:
        agent_skills = set(agent.get("skills") or [])
        task_skills = set(task_tags)
        
        if not task_skills:
            continue
        
        # 计算匹配度
        match = len(agent_skills & task_skills)
        score = match / len(task_skills)
        
        if score > best_score:
            best_score = score
            best_match = agent
    
    return best_match

# ============ 进度监控 ============

def check_stuck_tasks(project_id: int = None) -> List[Dict]:
    """检查停滞的任务（running 超过4小时）"""
    # 调用 API 获取 running 状态的任务
    resp = requests.get(
        f"{TASK_SERVICE_URL}/tasks",
        params={"status": "running", "project_id": project_id}
    )
    tasks = resp.json()
    
    stuck = []
    for task in tasks:
        if task.get("started_at"):
            started = datetime.fromisoformat(task["started_at"].replace('Z', '+00:00'))
            elapsed = (datetime.now() - started).total_seconds() / 3600
            
            if elapsed > 4:  # 超过4小时
                stuck.append(task)
    
    return stuck

def generate_project_report(project_id: int) -> str:
    """生成项目进度报告"""
    progress = get_project_progress(project_id)
    tasks = get_project_tasks(project_id)
    
    lines = [
        f"## 📊 项目进度报告: {progress['project_name']}",
        f"",
        f"**总体进度**: {progress['progress_percent']}%",
        f"",
        f"**任务统计**:",
        f"- 总任务: {progress['total_tasks']}",
        f"- 待办: {progress['stats']['pending']}",
        f"- 已分配: {progress['stats']['assigned']}",
        f"- 进行中: {progress['stats']['running']}",
        f"- 待验收: {progress['stats']['reviewing']}",
        f"- 已完成: {progress['stats']['completed']}",
        f"- 失败: {progress['stats']['failed']}",
        f"- 已拒绝: {progress['stats']['rejected']}",
        f"",
        f"**进行中的任务**:",
    ]
    
    running = [t for t in tasks if t['status'] == 'running']
    if running:
        for t in running:
            lines.append(f"- 🔄 #{t['id']} {t['title']} (@{t['assignee_agent']})")
    else:
        lines.append("- 无")
    
    lines.append("")
    lines.append("**待验收任务**:")
    
    reviewing = [t for t in tasks if t['status'] == 'reviewing']
    if reviewing:
        for t in reviewing:
            lines.append(f"- ✅ #{t['id']} {t['title']} (@{t['assignee_agent']})")
    else:
        lines.append("- 无")
    
    return "\n".join(lines)

# ============ 通知模板 ============

def format_new_project_notification(project: Dict, tasks: List[Dict]) -> str:
    """格式化新项目通知"""
    lines = [
        f"## 🚀 新项目创建: {project['name']}",
        f"",
        f"**描述**: {project.get('description', '无')}",
        f"",
        f"**已拆分 {len(tasks)} 个任务**:",
    ]
    
    for i, task in enumerate(tasks, 1):
        lines.append(f"{i}. **{task['title']}** (优先级: {task['priority']})")
        lines.append(f"   - 类型: {task['task_type']}")
        lines.append(f"   - 预计工时: {task.get('estimated_hours', '未估计')}h")
        if task.get('task_tags'):
            lines.append(f"   - 标签: {', '.join(task['task_tags'])}")
        lines.append("")
    
    lines.append("Agent 可以开始认领任务了！")
    
    return "\n".join(lines)

def format_task_reassigned_notification(task: Dict, reason: str) -> str:
    """格式化任务重分配通知"""
    return f"""## 🔄 任务重分配

**任务**: #{task['id']} {task['title']}
**原因**: {reason}
**状态**: 已重置为待办，等待新的 Agent 认领
"""
```

## 工作流程

### 1. 创建项目并自动拆分

```
Human: 帮我创建一个 AI 助手调研项目

PM Agent:
1. create_project("AI 助手调研", "调研当前主流 AI 助手...")
2. auto_breakdown(project_id, type="content")
3. 回复:

## 🚀 新项目创建: AI 助手调研
**已拆分 6 个任务**:
1. **内容策划** (优先级: 10)
   - 类型: analysis
   - 预计工时: 2h
...

Agent 可以开始认领任务了！
```

### 2. 监控项目进度

```
Human: 项目进度如何？

PM Agent:
1. get_project_progress(project_id)
2. 回复:

## 📊 项目进度报告: AI 助手调研
**总体进度**: 65%

**任务统计**:
- 总任务: 6
- 待办: 1
- 进行中: 1
- 待验收: 1
- 已完成: 3
...
```

### 3. 协调资源

```
PM Agent 发现任务堆积:
1. check_stuck_tasks()
2. 自动释放超时的任务
3. 通知相关 Agent

## 🔄 任务重分配
**任务**: #5 内容审核
**原因**: 任务已进行 5 小时，可能卡住
**状态**: 已重置为待办
```

## 集成到 Agent

```python
# 在 project-manager Agent 的 SOUL.md 中:
你是项目经理，负责协调团队完成项目。

你有以下能力：
1. 创建项目并拆分任务
2. 监控项目进度
3. 协调资源分配
4. 处理异常情况

当用户提到"创建项目"、"拆分任务"、"项目进度"时，
使用 project-manager skill 中的工具函数。
```
