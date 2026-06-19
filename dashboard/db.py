"""
Read-only DB access for the dashboard. Never writes — algo engine owns all writes.
Cached connection per Streamlit session via st.cache_resource.
"""
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import DB_PATH


@st.cache_resource
def get_engine():
    return create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def get_session():
    Session = sessionmaker(bind=get_engine())
    return Session()
