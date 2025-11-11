from datetime import datetime, date
from typing import Literal
import httpx
import pandas as pd 
import numpy as np
from config import settings
import asyncio
from dataclasses import dataclass, field
import streamlit as st 




@dataclass
class Message:
    from_: str
    to: str 
    body: str
    date_sent: str
    sid: str
    status: str
    unit_price: float
    num_segments: int
    error_code: None | str
    direction: Literal["undelivered", "read", "delivered", "received", "failed", "sent"]
    

@dataclass
class Filter:
    start_date: date 
    end_date: date 
    from_: str | None 
    to: str | None 
    status: Literal["Delivered", "Received", "Sent", "Failed", "Undelivered", "Read"] | None
    

    
@dataclass
class MessageMetric:
    msg_count: int 
    price: float 
    

@dataclass
class MessageKPIS:
    delivered: MessageMetric 
    sent: MessageMetric 
    received: MessageMetric
    undelivered: MessageMetric
    failed: MessageMetric
    read: MessageMetric
    
    total: MessageMetric = field(init = False, default = None)
    
    def __post_init__(self):
        self.total = self._compute_total()
        
            
    def _compute_total(self):
        metrics = [
            m for m in [
                self.read,
                self.delivered,
                self.received,
                self.sent,
                self.failed,
                self.undelivered
            ]
            if m is not None
        ]
        
        total_messages = sum(m.msg_count for m in metrics)
        total_price = sum(m.price for m in metrics)

        return MessageMetric(
            msg_count = total_messages,
            price = total_price
        )

    

async def fetch_raw_data():
    
    all_msgs: list[dict] = []
    
    endpoint: str = f"https://api.twilio.com/2010-04-01/Accounts/{settings.account_sid}/Messages.json?PageSize=5000"
    
    next_url: str = endpoint
    
    async with httpx.AsyncClient(follow_redirects = True) as aclient:
        
        while next_url:
            
            res = await aclient.get(next_url, auth = (settings.account_sid, settings.auth_token))
            res.raise_for_status()
            data = res.json()
            
            all_msgs.extend(data["messages"])
            next_url = data.get("next_page_uri")
            
            print(f"Next page uri is {next_url}")
            if next_url:
                next_url = "https://api.twilio.com" + next_url
    
            
        return all_msgs
     


def format_as_message(msg: dict) -> Message:
    
    return Message(
        from_ = msg["from"],
        to = msg["to"],
        date_sent = msg["date_sent"],
        unit_price = msg["price"],
        status = msg["status"],
        num_segments = msg["num_segments"],
        body = msg["body"],
        sid = msg["sid"],
        error_code = msg["error_code"],
        direction = msg["direction"]
    )


async def get_data():
    
    raw_data: list[dict] = await fetch_raw_data()
    
    messages: list[Message] = list(map(lambda msg: format_as_message(msg), raw_data))
    
    messages_df: pd.DataFrame = pd.DataFrame(messages)
    # Change the date_sent column into datetime
    messages_df["date_sent"] = pd.to_datetime(messages_df["date_sent"]).dt.tz_convert("Asia/Kolkata")
    
    expected_column_order: list[str] = ["from_", "to", "body", "date_sent", "sid", "status", "unit_price", "num_segments", "error_code", "direction"]
    
    messages_df = messages_df[expected_column_order]
    
    # Need to change the price column Values.
    
    messages_df["unit_price"] = messages_df["unit_price"].replace({None: 0}).astype(float)
    
    # Calculate total price by multiplying unit_price and num_sengments.
    
    messages_df["total_price"] = messages_df["unit_price"] * messages_df["num_segments"].astype(int)
    
    
    return messages_df

 


def filter_data(filters: Filter, df: pd.DataFrame): 
    
    # Filter the dataset with start and end_date first. 
    df = df[
        (df["date_sent"].dt.date >= filters.start_date) & 
        (df["date_sent"].dt.date <= filters.end_date)
    ]
    # print(df)
    
    if filters.from_:
        df = df[df["from_"] == filters.from_]
    if filters.to:
        df = df[df["to"] == filters.to]
    if filters.status:
        df = df[df["status"] == filters.status]
        
    return df    

    
StatusLike = Literal[
    "Delivered", "Received", "Sent", 
    "Failed", "Undelivered", "Read"
] | Literal[
    "delivered", "received", "sent", 
    "failed", "undelivered", "read"
]
      

def calulate_price(
    status: StatusLike,
    df: pd.DataFrame
):
   # Filter the message based on status. 
    status_df = df[df["status"] == status.lower()]
    return MessageMetric(
        price = round(status_df["total_price"].sum(), 4),
        msg_count =  status_df.shape[0]
    )
    
    
    
def get_message_kpis(df: pd.DataFrame):
    
    kpis: dict[str, MessageMetric] =  {
        status : calulate_price(status= status, df = df) 
        for status in ["delivered", "received", "sent", "failed", "undelivered", "read"]
    }  
    
    kpis: MessageKPIS = MessageKPIS(**kpis)
    
    return kpis


    
    
     
async def main():
    
    # Initalize session state variables.
    if "messages_df" not in st.session_state:
        st.session_state["messages_df"] = None 
        
    st.set_page_config(page_title = "Twilio Dashboard", page_icon = "dashboard", layout = "wide")
    st.title("Twilio Resource Usage Dashboard")
    
    if st.session_state["messages_df"] is None:    
        with st.spinner("Your data is getting fetched...", show_time = True):
            st.session_state["messages_df"] = await get_data()
        
    
    data_tab, visualization_tab = st.tabs(["Data", "Graph"])
    
    
    with data_tab:
        
        st.text("Programmable Messaging Logs")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        # st.sidebar.write("Hello")
        # Get the minimum date from the data. 
        min_date = st.session_state["messages_df"]["date_sent"].min().date()
        today: datetime = datetime.today()
        first_day_of_current_month: datetime = datetime(today.year, today.month, 1)
        
        start_date: date = col1.date_input("Start Date", key = "start_date", min_value = min_date, value = first_day_of_current_month, max_value = today)
        end_date: date = col2.date_input("End Date", key = "end_date", min_value = min_date,  max_value = today, value = today)

        # Unique message status options
        status_options: list = st.session_state["messages_df"]["status"].unique().tolist()
        status_options: list = list(map(lambda x: x.title(), status_options))
        status: str = col3.selectbox("Status", options = ["Select"] + status_options, key = "status")
        
        # from and to select box. 
        
        from_options: list = st.session_state["messages_df"]["from_"].unique().tolist()
        to_options: list = st.session_state["messages_df"]["to"].unique().tolist()
        
        # r2col1, r2col2, r2col3 = st.columns([0.5, 2, 0.5])
        from_ = col4.selectbox("From", options = ["Select"] + from_options, key = "from_")
        to = col5.selectbox("To", options = ["Select"] + to_options, key = "to")
        
        if start_date > end_date:
            _, error_col, _ = st.columns(3)
            error_col.error("Start Date should be less than End Date.")
            st.stop()
        
        
        # Get all the filter params.
        filters: Filter = Filter(
            start_date = start_date,
            end_date = end_date,
            from_ = from_ if from_ != "Select" else None,
            to = to if to != "Select" else None,
            status = status.lower() if status != "Select" else None
        )
        
        filtered_df = filter_data(
            filters = filters,
            df = st.session_state["messages_df"]
        )
        
        msg_kpis: MessageKPIS = get_message_kpis(filtered_df)
        
        col1.metric(
            label = "Total Messages", 
            value = msg_kpis.total.msg_count,
            delta = msg_kpis.total.price, 
            help = "Total numbers messages sent.", 
            border = True
        )
        
        col2.metric(
            label = "Delivered", 
            help = "Delivered Messages", border = True,
            delta = msg_kpis.delivered.price,
            value = msg_kpis.delivered.msg_count
        )
        
        col3.metric(
            label = "Undelivered", 
            value = msg_kpis.undelivered.msg_count,
            delta = msg_kpis.undelivered.price, 
            help = "Undelivered Messages", 
            border = True
        )
        col4.metric(
            label = "Failed", 
            value = msg_kpis.failed.msg_count,
            delta = msg_kpis.failed.price, 
            help = "Failed Message due to programatical issue.", 
            border = True
        )
        col5.metric(
            label = "Read", 
            value = msg_kpis.read.msg_count,
            delta = msg_kpis.read.price, 
            help = "Read Messages", 
            border = True
        )
        col1.metric(
            label = "Received", 
            value = msg_kpis.received.msg_count,
            delta = msg_kpis.received.price, 
            help = "Received Messages", 
            border = True
        )
        col2.metric(
            label = "Sent", 
            value = msg_kpis.sent.msg_count,
            delta = msg_kpis.sent.price, 
            help = "Sent Messages", 
            border = True
        )
        
        st.dataframe(filtered_df)
    

    
    


if __name__ == "__main__":
    asyncio.run(main())
    



