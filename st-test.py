from streamlit.testing.v1 import AppTest

def sttest():
    at = AppTest.from_file("dev.py")
    
    at.run()
if __name__ == "__main__":
    sttest()