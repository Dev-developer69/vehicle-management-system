import streamlit as st
import base64


def get_base64_image(image_path):
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return data

def image_backgroung():
    img_data = get_base64_image("cv-banner.jpg")

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
            background: rgba(0, 0, 0, 0.7);
            z-index: 0;
        }}
    </style>    
""", unsafe_allow_html=True)


def home_layout():
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@100..900&display=swap');  
            @import url('https://fonts.googleapis.com/css2?family=Climate+Crisis:YEAR@1979&display=swap');

            .stApp {
                background: #1A1A2E !important;
            }

            #MainMenu, header {
                visibility: hidden;
    }

            .block-container {
                padding-top: 2.5rem !important;
            }

            h2 {
                font-family: 'Outfit', sans-serif !important;
                font-size: 2.5rem !important;
            }   

            h3, h4 {
                font-family: 'Outfit', sans-serif !important;
                color: #7B8CFF !important;
            }
            button[kind="primary"] {
                background: #7B2FBE !important;
                background-color: #7B2FBE !important;
                border-color: #7B2FBE !important;
                border-radius: 1.5rem !important;
                color: white !important;
                padding: 5px 2px !important;
                transition: transform 0.3s ease-in-out !important;
            }
 
            button[kind="primary"]:hover,
            button[kind="primary"]:focus,
            button[kind="primary"]:active {
                background: #48CAE4 !important;
                background-color: #48CAE4 !important;
                border-color: #9B59B6 !important;
                transform: scale(0.95) !important;
            }
 
            /* Secondary buttons — indigo blue */
            button[kind="secondary"] {
                background: #5865F2 !important;
                background-color: #5865F2 !important;
                border-color: #5865F2 !important;
                border-radius: 1.5rem !important;
                color: white !important;
                padding: 5px 2px !important;
                transition: transform 0.3s ease-in-out !important;
            }
 
            button[kind="secondary"]:hover,
            button[kind="secondary"]:focus,
            button[kind="secondary"]:active {
                background: #0F3460   !important;
                background-color: #0F3460   !important;
                border-color: #7B8CFF !important;
                transform: scale(0.95) !important
            }
                
            button[kind="tertiary"] {
                background: #2D6A4F !important;
                background-color: #2D6A4F !important;
                border: none !important;
                border-radius: 1.5rem !important;
                color: white !important;
                padding: 5px 2px !important;
                transition: transform 0.3s ease-in-out !important;
}

            button[kind="tertiary"]:hover {
                background: #48CAE4 !important;
                transform: scale(0.95) !important;
            }
            
        </style>
    """, unsafe_allow_html=True)

def background():
    st.markdown('''
    <style>
            .stApp {
                background: #12122A !important;
            }

            #MainMenu, header {
                visibility: hidden;
            }

            .block-container {
                padding-top: 0.5rem !important;
            }

            /* Primary buttons — purple */
            button[kind="primary"] {
                background: #9B59B6  !important;
                border-radius: 1.5rem !important;
                color: white !important;
                padding: 5px 2px !important;
                transition: transform 0.3s ease-in-out !important;
            }

            button[kind= "primary"]:hover {
                background: #9B59B6 !important;
                transform: scale(0.95) !important;
            }

            /* Secondary buttons — indigo blue */
            button[kind="secondary"] {
                background: #5865F2 !important;
                border-radius: 1.5rem !important;
                color: white !important;
                padding: 5px 2px !important;
                transition: transform 0.3s ease-in-out !important;
            }

            button[kind="secondary"]:hover {
                background: #7B8CFF !important;
                transform: scale(0.95) !important;
            }

            button[kind="tertiary"] {
                background: #2D6A4F !important;
                background-color: #2D6A4F !important;
                border: none !important;
                border-radius: 1.5rem !important;
                color: white !important;
                padding: 5px 2px !important;
                transition: transform 0.3s ease-in-out !important;
}

            button[kind="tertiary"]:hover {
                background: #48CAE4 !important;
                transform: scale(0.95) !important;
            }
    </style>
''', unsafe_allow_html=True)
    


