import os, json, glob
from datetime import datetime

class Memory:
    """Structured storage for execution history"""
    
    def __init__(self, args, item: dict):

        self.save_dir = args.save_dir
        self.unique_id = item["UID"]
        self.file_path = self.get_filepath()
        self.metadata = {
            "question": item["question"],
            "answer": item["answer"],
            "strategy": args.strategy,
            "code_llm": args.code_llm,
            "answer_llm": args.answer_llm,
            "language": args.language,
            "max_iters": args.max_iters,
            "suffix": args.suffix,
            "timestamp": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
            "url": item["URL"],
            "unique_id": item["UID"],
        }
        self.data = []

    def get_filepath(self) -> str:
        """Get the filepath for this memory instance"""
        return os.path.join(self.save_dir, f"memory_{self.unique_id}.json")
    
    def exists(self) -> bool:
        if os.path.exists(self.file_path):
            return True
        else:
            return False

    def log_iter(self, iter_idx, info: dict):

        temp = {
            "iter": iter_idx,
            "raw_code": info.get("raw_code"),
            "code": info.get("code"),
            "exec_msg": info.get("exec_msg"),
            "exec_stderr": info.get("exec_stderr"),
            "exec_returncode": info.get("exec_returncode"),
            "raw_answer": info.get("raw_answer"),
            "answer": info.get("answer"),
            "answer_thinking": info.get("answer_thinking"),
            "system_prompt": info.get("system_prompt"),
            "dataset_choice": info.get("dataset_choice"),
        }
        self.data.append(temp)

    def save(self):
        result = {"metadata": self.metadata, "data": self.data}
        with open(self.file_path, "w") as f:
            json.dump(result, f, indent=4)

    def load(self, file_path):
        with open(file_path, "r") as f:
            data = json.load(f)
        self.metadata = data["metadata"]
        self.data = data["data"]

def set_info(question,
             raw_code=None, code=None, 
             exec_msg=None, exec_stderr=None, exec_returncode=None,
             raw_answer=None, answer=None, answer_thinking=None, 
             system_prompt=None, dataset_choice=None
             ):
    info = {
        "question": question,
        "raw_code": raw_code, 
        "code": code,
        "exec_msg": exec_msg,
        "exec_stderr": exec_stderr,
        "exec_returncode": exec_returncode,
        "raw_answer": raw_answer,
        "answer": answer,
        "answer_thinking": answer_thinking,
        "system_prompt": system_prompt,
        "dataset_choice": None,
    }
    return info