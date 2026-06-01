import streamlit as st
import base64


def get_base64_image(image_path):
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return data

def image_backgroung():
    with open(r"E:\my projcts\vehicle maintanance system\cv-banner.jpg", "rb") as f:
        img_data = base64.b64encode(f.read()).decode()

    st.markdown(f"""
    <style>
        .stApp {{
            background-image: url('data:image/jpeg;base64,{img_data}') !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
        }}

        .stApp::before {{
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);  /* black overlay, 0.5 = 50% dark */
            z-index: 0;
        }}
        
    </style>    
""", unsafe_allow_html=True)


def home_layout():

    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@100..900&display=swap');  
            @import url('https://fonts.googleapis.com/css2?family=Climate+Crisis:YEAR@1979&display=swap');

            
            #MainMenu, header {
                visibility: hidden;
            }
            
            *{
                overflow : hidden;}
            
            .block-container{
                padding-top:2.5rem !important;
            }

            h2 {
                font-family:'Outfit',san-serif !important;
                font-size: 2.5rem !important;
                color: pink !important;
            }
            
            h3,h4{
                font-family: 'outfit', sans-sarif !important;
                color: red !important;
            }
            
            button[kind= 'primary']{
                # background:#5865F2 !important;
                border-radius: 1.5rem !important;
                color: white !important;
                padding: 5px 2px !important;
                transition :transform 0.5s ease-in-out !important ;   
            }    
            
            button[kind='secondary']{
                background:#EB459E !important;
                border-radius: 1.5rem !important;
                color: white !important;
                padding: 5px 2px !important;
                transition :transform 0.5s ease-in-out !important ;   
            }
                
            button:hover[kind='secondary']{
                transform: scale(1.2)}
            
        </style>
    """, unsafe_allow_html=True)