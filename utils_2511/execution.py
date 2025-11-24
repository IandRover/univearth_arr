import os, re, time, subprocess

def _clean_ee_message(text: str) -> str:
    """Remove Earth Engine feedback message from output."""
    ee_pattern = r"\*\*\* Earth Engine \*\*\* Share your feedback.*?source=Init\n"
    return re.sub(ee_pattern, '', text)

def execute_code(code: str, timeout: int = 120, language: str = "python") -> dict:

    assert language.lower() in ["python", "javascript"], "Language must be either 'python' or 'javascript'"
    try:
        if language.lower() == "python":
            random_file_name = f"./temp/{str(time.time()).replace('.', '')}.py"
        elif language.lower() == "javascript":
            random_file_name = f"./temp/{str(time.time()).replace('.', '')}.js"
        
        with open(random_file_name, "w", encoding='utf-8') as f:
            code = code.encode('utf-8', errors='ignore').decode('utf-8')
            f.write(code)
        
        start_time = time.time()
        if language.lower() == "python":
            result = subprocess.run(
                ["python", random_file_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout
            )
        elif language.lower() == "javascript":
            result = subprocess.run(
                ["node", random_file_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout
            )
        
        if os.path.exists(random_file_name):
            try:
                os.remove(random_file_name)
            except Exception:
                pass

        stderr = _clean_ee_message(result.stderr.decode("utf-8"))
        stdout = _clean_ee_message(result.stdout.decode("utf-8"))

        return {
            "exec_msg": stdout,
            "exec_stderr": stderr,
            "exec_returncode": result.returncode
        }
    
    except subprocess.TimeoutExpired:
        if os.path.exists(random_file_name):
            os.remove(random_file_name)
        return {
            "exec_msg": "",
            "exec_stderr": f"Execution timed out after {timeout} seconds",
            "exec_returncode": 1
        }
    
    except Exception as e:
        if os.path.exists(random_file_name):
            os.remove(random_file_name)
        return {
            "exec_msg": "",
            "exec_stderr": str(e),
            "exec_returncode": 1
        }
