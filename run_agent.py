import argparse
import os
import sys
from dotenv import load_dotenv

# Ensure projects/Agents directory is in python path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.config import load_config

def main():
    # Load environment variables from .env if present
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Multi-Agent CLI Runner")
    parser.add_argument("--agent", default="data_analyst", help="Agent identifier to run (e.g. data_analyst)")
    parser.add_argument("--data", help="Path to the dataset (CSV)")
    parser.add_argument("--question", help="Question to answer")
    parser.add_argument("--config", help="Path to agent spec.yaml (defaults to <agent>/spec.yaml)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging and execution timing")
    
    args = parser.parse_args()
    
    agent_name = args.agent
    agent_dir = os.path.join(BASE_DIR, agent_name)
    
    if not os.path.exists(agent_dir):
        print(f"Error: Agent directory '{agent_name}' not found at {agent_dir}")
        sys.exit(1)
        
    # Resolve config path
    config_path = args.config
    if not config_path:
        config_path = os.path.join(agent_dir, "spec.yaml")
    elif not os.path.isabs(config_path):
        config_path = os.path.join(BASE_DIR, config_path)
        
    # Resolve default data path & question for data_analyst if not provided
    data_path = args.data
    if not data_path and agent_name == "data_analyst":
        data_path = os.path.join(agent_dir, "sample_data", "sales.csv")
    elif data_path and not os.path.isabs(data_path):
        data_path = os.path.join(BASE_DIR, data_path)
        
    question = args.question
    if not question and agent_name == "data_analyst":
        question = "What are the top 3 products by total revenue?"
        
    output_dir = os.path.join(agent_dir, "outputs")
    
    try:
        config = load_config(config_path)
        config["verbose"] = args.verbose
        
        if agent_name == "data_analyst":
            from data_analyst.agent import DataAnalystAgent
            agent = DataAnalystAgent(config=config, output_dir=output_dir)
            agent.run(data_path=data_path, question=question)
        else:
            print(f"Error: Runner for agent '{agent_name}' is not registered in run_agent.py")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error executing agent '{agent_name}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
