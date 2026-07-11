import os

class SOPRouter:
    def __init__(self, sops_dir=None):
        if sops_dir is None:
            # Resolve sops/ directory relative to agent/sops.py
            current_dir = os.path.dirname(os.path.abspath(__file__))
            sops_dir = os.path.join(current_dir, "..", "sops")
        self.sops_dir = os.path.abspath(sops_dir)

    def route(self, question: str) -> tuple:
        """
        Routes the user's question to the most relevant SOP.
        Returns a tuple of (sop_file_name, sop_content).
        """
        q_lower = question.lower()
        
        cleaning_keywords = [
            "clean", "null", "missing", "nan", "duplicate", "outlier", 
            "filter", "preprocess", "typecast", "imput"
        ]
        visualization_keywords = [
            "plot", "chart", "graph", "visualize", "bar", "line", 
            "scatter", "histogram", "plt", "figure", "draw"
        ]
        
        if any(kw in q_lower for kw in cleaning_keywords):
            sop_file = "data_cleaning.md"
        elif any(kw in q_lower for kw in visualization_keywords):
            sop_file = "visualization.md"
        else:
            sop_file = "default_analyst.md"
            
        sop_path = os.path.join(self.sops_dir, sop_file)
        
        try:
            with open(sop_path, "r", encoding="utf-8") as f:
                content = f.read()
            return sop_file, content
        except Exception as e:
            # Safe fallback if file read fails
            fallback_msg = f"Standard data analyst guidelines.\n(Error loading dynamic SOP: {e})"
            return "fallback", fallback_msg
