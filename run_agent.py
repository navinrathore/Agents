import argparse
import os
from dotenv import load_dotenv
from agent.config import load_config
from agent.analyst import DataAnalystAgent

def main():
    # Load environment variables from .env if present
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Run the Data Analyst Agent")
    parser.add_argument("--data", required=True, help="Path to the dataset (CSV)")
    parser.add_argument("--question", required=True, help="Question to answer")
    parser.add_argument("--config", default="spec.yaml", help="Path to agent spec.yaml")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging and execution timing")
    
    args = parser.parse_args()
    
    # Resolve absolute paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, args.config)
    data_path = os.path.join(base_dir, args.data) if not os.path.isabs(args.data) else args.data
    output_dir = os.path.join(base_dir, "outputs")
    
    try:
        config = load_config(config_path)
        config["verbose"] = args.verbose
        
        agent = DataAnalystAgent(config=config, output_dir=output_dir)
        agent.run(data_path=data_path, question=args.question)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
