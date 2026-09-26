# Dette scriptet lager et dashbord ved hjelp av Streamlit

# pip install streamlit
# streamlit run dashboard.py
import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="AI Cyber Arena", layout="wide")
st.title("AI Security Dashboard",text_alignment="center")
st.markdown("This is a dashboard to get an overview over the attacks on our web application",text_alignment="center")


# Sjekk om filen finnes
if os.path.exists("web_logger.txt"):
    # pandas leser JSON-filen og gjør den om til en tabell automatisk!
    df = pd.read_json("web_logger.txt", lines=True)

    if len(df) > 0:
        totale_forsøk = len(df)
        # Teller hvor mange ganger statusen var 200 OK (angriper kom igjennom)
        vellykkede_angrep = len(df[df['status'] == 200])
        suksessrate = (vellykkede_angrep / totale_forsøk) * 100
        
        # Vis prosenten i en stor, pen boks
        st.metric(
            label="Angriperens suksessrate (Skal presses ned til 0%)", 
            value=f"{suksessrate:.1f}%", 
            border = True,
            delta="AI må patche koden!" if suksessrate > 0 else "Siden er trygg",
            delta_color="inverse"
        )
    
    # Vis tabellen på skjermen (nyeste øverst)
    st.dataframe(df.iloc[::-1], use_container_width=True)
else:
    st.error("Finner ikke web_logger.txt")







