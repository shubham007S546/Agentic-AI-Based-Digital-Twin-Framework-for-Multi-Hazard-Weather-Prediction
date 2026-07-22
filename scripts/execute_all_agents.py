import asyncio
import sys
import os
import time
from pathlib import Path

# Force UTF-8 output formatting for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.core.enums import AgentName, AgentTrigger
from app.agents.agent_registry import get_agent_registry
from app.agents import (
    WeatherAgent,
    PredictionAgent,
    AlertAgent,
    DisasterIntelligenceAgent,
    DigitalTwinAgent,
    ReportAgent,
    NotificationAgent,
    MonitoringAgent,
    DataCollectionAgent,
    ResearchAgent,
    ExplainabilityAgent,
    DecisionSupportAgent,
    OrchestratorAgent
)

def register_all_agents():
    registry = get_agent_registry()
    registry.register(WeatherAgent())            # WEATHER_INTELLIGENCE
    registry.register(PredictionAgent())         # PREDICTION
    registry.register(AlertAgent())              # ALERT
    registry.register(DisasterIntelligenceAgent())  # DISASTER_INTELLIGENCE
    registry.register(DigitalTwinAgent())        # DIGITAL_TWIN
    registry.register(ReportAgent())             # REPORT_GENERATOR
    registry.register(NotificationAgent())       # NOTIFICATION
    registry.register(MonitoringAgent())         # MONITORING
    registry.register(DataCollectionAgent())     # DATA_COLLECTION
    registry.register(ResearchAgent())           # RESEARCH
    registry.register(ExplainabilityAgent())     # EXPLAINABILITY
    registry.register(DecisionSupportAgent())    # DECISION_SUPPORT
    return registry

async def run_all_agents():
    registry = register_all_agents()
    print("=" * 80)
    print("🤖 RUNNING ALL 12 AGENTS IN MULTI-AGENT PIPELINE")
    print("=" * 80)
    
    registered_agents = registry.list_agents()
    print(f"Total Registered Agents in System: {len(registered_agents)}")
    for idx, ag in enumerate(registered_agents, 1):
        print(f"  {idx:2d}. [{ag['name']}] v{ag['version']} - {ag['description']}")
    
    print("\n" + "-" * 80)
    print("🚀 EXECUTING PIPELINE CYCLE ACROSS ALL AGENTS")
    print("-" * 80)
    
    # Context payload passed between agents in the pipeline
    payload = {
        "district": "Mandi",
        "state": "Himachal Pradesh",
        "latitude": 31.7087,
        "longitude": 76.9320,
        "date": "2026-07-22",
        "force_refresh": True
    }
    
    execution_results = []
    
    # List of agent enums to execute in dependency order
    agents_to_run = [
        AgentName.DATA_COLLECTION,
        AgentName.WEATHER_INTELLIGENCE,
        AgentName.PREDICTION,
        AgentName.ALERT,
        AgentName.DISASTER_INTELLIGENCE,
        AgentName.DIGITAL_TWIN,
        AgentName.EXPLAINABILITY,
        AgentName.DECISION_SUPPORT,
        AgentName.REPORT_GENERATOR,
        AgentName.NOTIFICATION,
        AgentName.RESEARCH,
        AgentName.MONITORING,
    ]
    
    start_time = time.time()
    
    for agent_enum in agents_to_run:
        agent_name = agent_enum.value
        print(f"\n▶ Running Agent: {agent_name}...")
        try:
            result = await registry.execute(
                agent_name=agent_enum,
                payload=payload,
                trigger=AgentTrigger.SCHEDULED,
                triggered_by="orchestrator_main"
            )
            
            status_str = result.status.value if hasattr(result.status, 'value') else str(result.status)
            duration = round(result.duration_seconds or 0, 3)
            
            # Save output into context for downstream agents if returned
            if result.result_summary and isinstance(result.result_summary, dict):
                payload.update(result.result_summary)
                
            execution_results.append({
                "agent": agent_name,
                "status": status_str,
                "duration": duration,
                "summary": str(result.result_summary),
                "error": result.error_message
            })
            
            print(f"  └─ Status: {status_str} | Time: {duration}s")
            print(f"  └─ Output Summary: {result.result_summary}")
            
        except Exception as e:
            print(f"  └─ Exception: {str(e)}")
            execution_results.append({
                "agent": agent_name,
                "status": "FAILED",
                "duration": 0,
                "summary": "Execution raised an exception",
                "error": str(e)
            })

    total_time = round(time.time() - start_time, 3)
    
    print("\n" + "=" * 80)
    print("📊 AGENT PIPELINE EXECUTION SUMMARY")
    print("=" * 80)
    print(f"{'Agent Name':<28} | {'Status':<10} | {'Duration (s)':<12} | {'Output Summary'}")
    print("-" * 90)
    for res in execution_results:
        summary_clip = (res['summary'] or '')[:45]
        print(f"{res['agent']:<28} | {res['status']:<10} | {res['duration']:<12} | {summary_clip}")
    print("=" * 90)
    print(f"Total Execution Time for All 12 Agents: {total_time} seconds\n")

if __name__ == "__main__":
    asyncio.run(run_all_agents())
