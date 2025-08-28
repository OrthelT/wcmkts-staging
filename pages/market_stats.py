import os
import sys
import time

from db_handler import get_market_data
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import text
from sqlalchemy.orm import Session
from db_handler import  *
from sync_scheduler import initialize_sync_state, check_sync_status
from logging_config import setup_logging
import millify
from config import DatabaseConfig
from sync_state import sync_state


# Insert centralized logging configuration
logger = setup_logging(__name__)

# Log application start
logger.info("Application started")
logger.info(f"streamlit version: {st.__version__}")
logger.info("-"*100)

mkt_db = DatabaseConfig("wcmkt3")
sde_db = DatabaseConfig("sde")

# Function to get unique categories and item names
def get_filter_options(selected_categories=None):
    try:
        # First get type_ids from market orders
        mkt_query = """
        SELECT DISTINCT type_id
        FROM marketorders
        WHERE is_buy_order = 0
        """
        logger.info("getting filter options")
        with Session(mkt_db.engine) as session:
            result = session.execute(text(mkt_query))
            type_ids = [row[0] for row in result.fetchall()]

            if not type_ids:
                return [], []
            type_ids_str = ','.join(map(str, type_ids))

        logger.info(f"type_ids: {len(type_ids)}")

        # Then get category info from SDE database
        sde_query = f"""
        SELECT DISTINCT it.typeName as type_name, it.typeID as type_id, it.groupID as group_id, ig.groupName as group_name,
               ic.categoryID as category_id, ic.categoryName as category_name
        FROM invTypes it
        JOIN invGroups ig ON it.groupID = ig.groupID
        JOIN invCategories ic ON ig.categoryID = ic.categoryID
        WHERE it.typeID IN ({type_ids_str})
        """
        with Session(sde_db.engine) as session:
            result = session.execute(text(sde_query))
            df = pd.DataFrame(result.fetchall(),
                              columns=['type_name', 'type_id', 'group_id', 'group_name', 'category_id', 'category_name'])

            categories = sorted(df['category_name'].unique())

            if selected_categories:
                df = df[df['category_name'].isin(selected_categories)]

        items = sorted(df['type_name'].unique())


        return categories, items


    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return [], []

# Query function
def create_price_volume_chart(df):
    # Create histogram with price bins
    fig = px.histogram(
        df,
        x='price',
        y='volume_remain',
        histfunc='sum',  # Sum the volumes for each price point
        nbins=50,  # Adjust number of bins as needed
        title='Market Orders Distribution',
        labels={
            'price': 'Price (ISK)',
            'volume_remain': 'Volume Available'
        }
    )

    # Update layout for better readability
    fig.update_layout(
        bargap=0.1,  # Add small gaps between bars
        xaxis_title="Price (ISK)",
        yaxis_title="Volume Available",
        showlegend=False
    )

    # Format price labels with commas for thousands
    fig.update_xaxes(tickformat=",")

    return fig

def create_history_chart(type_id):
    df = get_market_history(type_id)
    if df.empty:
        return None
    fig = go.Figure()
    # Create subplots: 2 rows, 1 column, shared x-axis
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],  # Price gets more space than volume

    )

    # Add price line to the top subplot (row 1)
    fig.add_trace(
        go.Scatter(
            x=df['date'],
            y=df['average'],
            name='Average Price',
            line=dict(color='#FF69B4', width=2)  # Hot pink line
        ),
        row=1, col=1
    )

    # Add volume bars to the bottom subplot (row 2)
    fig.add_trace(
        go.Bar(
            x=df['date'],
            y=df['volume'],
            name='Volume',
            opacity=0.5,
            marker_color='#00B5F7',
            base=0,


              # Bright blue bars
        ),
        row=2, col=1
    )

    # Calculate ranges with padding
    min_price = df['average'].min()
    max_price = df['average'].max()
    price_padding = (max_price - min_price) * 0.05  # 5% padding
    min_volume = df['volume'].min()
    max_volume = df['volume'].max()

    # Update layout for both subplots
    fig.update_layout(
        title='Market History',
        paper_bgcolor='#0F1117',  # Dark background
        plot_bgcolor='#0F1117',   # Dark background
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1,
            xanchor="right",
            x=1,
            font=dict(color='white'),
            bgcolor='rgba(10,10,10,0)'  # Transparent background
        ),
        # margin=dict(t=50, b=50, r=20, l=50),
        title_font_color='white',
        # height=600,  # Taller to accommodate both plots
        hovermode='x unified',  # Show all data on hover
        autosize=True,
    )


    fig.update_yaxes(
        title=dict(text='Price (ISK)', font=dict(color='white', size=10), standoff=5),
        gridcolor='rgba(128,128,128,0.2)',
        tickfont=dict(color='white'),
        tickformat=",",
        row=1, col=1,
        automargin = True


    )

    # Update axes for the volume subplot (bottom)
    fig.update_yaxes(
        title=dict(text='Volume', font=dict(color='white', size=10), standoff=5),
        gridcolor='rgba(128,128,128,0.2)',
        tickfont=dict(color='white'),
        tickformat=",",
        row=2, col=1,
        automargin = True
    )

    # Update shared x-axis
    fig.update_xaxes(
        gridcolor='rgba(128,128,128,0.2)',
        tickfont=dict(color='white'),
        row=2, col=1  # Apply to the bottom subplot's x-axis
    )

    # Hide x-axis labels for top subplot
    fig.update_xaxes(
        showticklabels=False,
        row=1, col=1
    )

    return fig

def display_sync_status():
    """Display sync status in the sidebar."""
    time_since_esi_update = get_time_since_esi_update()
    st.sidebar.markdown(f"**Last ESI update:** {time_since_esi_update}")
    time_until_update = get_time_until_next_update()
    st.sidebar.markdown(f"*Next ESI update in {time_until_update}*")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Database Sync Status")
    status_color = "green" if st.session_state.sync_status == "Success" else "red"

    if st.session_state.last_sync:
        last_sync_time = st.session_state.last_sync.strftime("%Y-%m-%d %H:%M UTC")
        st.sidebar.markdown(f"**Last sync:** {last_sync_time}")
        if st.session_state.next_sync:
            next_sync_time = st.session_state.next_sync.strftime("%Y-%m-%d %H:%M UTC")
            st.sidebar.markdown(f"**Next scheduled sync:** {next_sync_time}")
    else:
        st.sidebar.markdown("**Last sync:** Not yet run")

    st.sidebar.markdown(f"**Status:** <span style='color:{status_color}'>{st.session_state.sync_status}</span>", unsafe_allow_html=True)

    # Manual sync button
    if st.sidebar.button("Sync Now"):
        try:
            mkt_db.sync()
            st.session_state.sync_status = "Success"
            st.rerun()
        except Exception as e:
            logger.error(f"st.session_state.sync_status: {st.session_state.sync_status}")
            st.sidebar.error(f"Sync failed: {str(e)}")

    if st.session_state.sync_status == "Success":
        st.sidebar.success("Database sync completed successfully!")

def main():
    logger.info("Starting main function")

    # Initialize all session state variables
    initialize_sync_state()

    # Check for sync needs using cached function
    logger.info("Checking sync status")
    sync_info = sync_state()
    sync_check = sync_info['sync_check']
    last_sync = sync_info['last_sync']
    next_sync = sync_info['next_sync']

    logger.info(f"sync_check: {sync_check}")
    logger.info(f"last_sync: {last_sync}")
    logger.info(f"next_sync: {next_sync}")
    sync_check = False

    if sync_check:
        logger.info("Sync needed, syncing now")
        mkt_db.sync()
        st.session_state.sync_status = "Success"
        st.rerun()
    else:
        logger.info(f"No sync needed: last sync: {st.session_state.last_sync}, next sync: {st.session_state.next_sync}\n")

    # if check_sync_status():
    #     logger.info("Sync needed, syncing now")
    #     mkt_db.sync()
    #     t2 = time.perf_counter()
    #     elapsed_time = (t2-t1)*1000
    #     logger.info(f"TIME sync_db() = {elapsed_time} ms")
    #     st.session_state.sync_status = "Success"
    #     st.session_state.update_time = get_update_time()
    #     logger.info(f"Sync status updated to: {st.session_state.sync_status}\n, last sync: {st.session_state.last_sync}\n, next sync: {st.session_state.next_sync}\n")
    #     st.rerun()
    # else:
    #     logger.info(f"No sync needed: last sync: {st.session_state.last_sync}, next sync: {st.session_state.next_sync}\n")

    wclogo = "images/wclogo.png"
    st.image(wclogo, width=150)

    # Title
    st.title("Winter Coalition Market Stats")

    # Sidebar filters
    st.sidebar.header("Filters")

    # Show all option
    show_all = st.sidebar.checkbox("Show All Data", value=False)

    logger.info("Getting initial categories")
    # Get initial categories
    categories, _ = get_filter_options()

    # Category filter - changed to selectbox for single selection
    selected_category = st.sidebar.selectbox(
        "Select Category",
        options=[""] + categories,  # Add empty option to allow no selection
        index=0,
        format_func=lambda x: "All Categories" if x == "" else x
    )

    # Convert to list format for compatibility with existing code
    selected_categories = [selected_category] if selected_category else []

    logger.info(f"Selected category: {selected_category}")

    # Debug info
    if selected_category:
        st.sidebar.text(f"Category: {selected_category}")

    # Get filtered items based on selected category
    _, available_items = get_filter_options(selected_categories if not show_all and selected_category else None)

    # Item name filter - changed to selectbox for single selection
    selected_item = st.sidebar.selectbox(
        "Select Item",
        options=[""] + available_items,  # Add empty option to allow no selection
        index=0,
        format_func=lambda x: "All Items" if x == "" else x
    )

    # Convert to list format for compatibility with existing code
    selected_items = [selected_item] if selected_item else []

    # Debug info
    if selected_item:
        st.sidebar.text(f"Item: {selected_item}")

    logger.info(f"Selected item: {selected_item}")


    t1 = time.perf_counter()

    sell_data, buy_data, stats = get_market_data(show_all, selected_categories, selected_items)

    # Main content
    t2 = time.perf_counter()
    elapsed_time = (t2-t1)*1000
    print("-"*100)
    logger.info(f"TIME get_market_data() = {round(elapsed_time, 2)} ms")
    print("-"*100)

    # Process sell orders
    sell_order_count = 0
    sell_total_value = 0
    if not sell_data.empty:
        sell_order_count = sell_data['order_id'].nunique()
        sell_total_value = (sell_data['price'] * sell_data['volume_remain']).sum()

    # Process buy orders
    buy_order_count = 0
    buy_total_value = 0
    if not buy_data.empty:
        buy_order_count = buy_data['order_id'].nunique()
        buy_total_value = (buy_data['price'] * buy_data['volume_remain']).sum()

    logger.info(f"sell_order_count: {sell_order_count}")
    logger.info(f"sell_total_value: {sell_total_value}")
    logger.info(f"buy_order_count: {buy_order_count}")
    logger.info(f"buy_total_value: {buy_total_value}")

    fit_df = pd.DataFrame()
    timestamp = None

    if not sell_data.empty:
        if len(selected_items) == 1:
            sell_data = sell_data[sell_data['type_name'] == selected_items[0]]
            if not buy_data.empty:
                buy_data = buy_data[buy_data['type_name'] == selected_items[0]]
            stats = stats[stats['type_name'] == selected_items[0]]
            type_id = sell_data['type_id'].iloc[0]
            if type_id:
                fit_df, timestamp = get_fitting_data(type_id)
            else:
                fit_df = pd.DataFrame()
                timestamp = None
        elif len(selected_categories) == 1:
            stats = stats[stats['category_name'] == selected_categories[0]]

        # Display metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if not sell_data.empty:
                min_price = stats['min_price'].min()
                if pd.notna(min_price) and selected_items:
                    display_min_price = millify.millify(min_price, precision=2)
                    st.metric("Sell Price (min)", f"{display_min_price} ISK")
            else:
                st.metric("Sell Price (min)", "0 ISK")

            if sell_total_value > 0:
                display_sell_total_value = millify.millify(sell_total_value, precision=2)
                st.metric("Market Value (sell orders)", f"{display_sell_total_value} ISK")
            else:
                st.metric("Market Value (sell orders)", "0 ISK")

        with col2:
            if not sell_data.empty:
                volume = sell_data['volume_remain'].sum()
                if pd.notna(volume):
                    display_volume = millify.millify(volume, precision=2)
                    st.metric("Market Stock (sell orders)", f"{display_volume}")
            else:
                st.metric("Market Stock (sell orders)", "0")

        with col3:
            days_remaining = stats['days_remaining'].min()
            if pd.notna(days_remaining) and selected_items:
                display_days_remaining = f"{days_remaining:.1f}"
                st.metric("Days Remaining", f"{display_days_remaining}")
            elif sell_order_count > 0:
                display_sell_order_count = f"{sell_order_count:,.0f}"
                st.metric("Total Sell Orders", f"{display_sell_order_count}")
            else:
                st.metric("Total Sell Orders", "0")

        with col4:
            isship = False
            try:
                cat_id = stats['category_id'].iloc[0]
                fits_on_mkt = fit_df['Fits on Market'].min()

                if cat_id == 6:
                    display_fits_on_mkt = f"{fits_on_mkt:,.0f}"
                    st.metric("Fits on Market", f"{display_fits_on_mkt}")
                    isship = True

            except:
                pass


        st.divider()
        # Display detailed data

        # Format the DataFrame for display with null handling
        display_df = sell_data.copy()

        #create a header for the item
        if len(selected_items) == 1:
            image_id = display_df.iloc[0]['type_id']
            type_name = display_df.iloc[0]['type_name']
            st.subheader(f"{type_name}", divider="blue")
            col1, col2 = st.columns(2)
            with col1:
                if isship:
                    st.image(f'https://images.evetech.net/types/{image_id}/render?size=64')
                else:
                    st.image(f'https://images.evetech.net/types/{image_id}/icon')
            with col2:
                try:
                    if fits_on_mkt:
                        st.subheader("Winter Co. Doctrine", divider="orange")
                        if cat_id in [7,8,18]:
                            st.write(get_module_fits(type_id))
                        else:
                            st.write(fit_df[fit_df['type_id'] == type_id]['group_name'].iloc[0])
                except:
                    pass
        elif selected_categories:
            cat_label = selected_categories[0]
            if cat_label.endswith("s"):
                cat_label = cat_label
            else:
                cat_label = cat_label + "s"
            st.subheader(f"Sell Orders for {cat_label}", divider="blue")
        else:
            st.subheader("All Sell Orders", divider="green")

        display_df.type_id = display_df.type_id.astype(str)
        display_df.order_id = display_df.order_id.astype(str)
        display_df.drop(columns='is_buy_order', inplace=True)
        # Format numeric columns safely
        numeric_formats = {
            'volume_remain': '{:,.0f}',
            'price': '{:,.2f}',
            'min_price': '{:,.2f}',
            'avg_of_avg_price': '{:,.2f}',
        }

        for col, format_str in numeric_formats.items():
            if col in display_df.columns:  # Only format if column exists
                display_df[col] = display_df[col].apply(lambda x: safe_format(x, format_str))

        st.dataframe(display_df, hide_index=True)

        # Display buy orders if they exist
        if not buy_data.empty:
            # Display buy orders header
            if len(selected_items) == 1:
                st.subheader(f"Buy Orders for {type_name}", divider="orange")
            elif selected_categories:
                cat_label = selected_categories[0]
                if cat_label.endswith("s"):
                    cat_label = cat_label
                else:
                    cat_label = cat_label + "s"
                st.subheader(f"Buy Orders for {cat_label}", divider="orange")
            else:
                st.subheader("All Buy Orders", divider="orange")

            # Display buy orders metrics
            col1, col2 = st.columns(2)
            with col1:
                if buy_total_value > 0:
                    st.metric("Market Value (buy orders)", f"{millify.millify(buy_total_value, precision=2)} ISK")
                else:
                    st.metric("Market Value (buy orders)", "0 ISK")

            with col2:
                if buy_order_count > 0:
                    st.metric("Total Buy Orders", f"{buy_order_count:,.0f}")
                else:
                    st.metric("Total Buy Orders", "0")

            # Format buy orders for display
            buy_display_df = buy_data.copy()
            buy_display_df.type_id = buy_display_df.type_id.astype(str)
            buy_display_df.order_id = buy_display_df.order_id.astype(str)
            buy_display_df.drop(columns='is_buy_order', inplace=True)

            # Format numeric columns safely
            for col, format_str in numeric_formats.items():
                if col in buy_display_df.columns:  # Only format if column exists
                    buy_display_df[col] = buy_display_df[col].apply(lambda x: safe_format(x, format_str))

            st.dataframe(buy_display_df, hide_index=True)

        # Display charts
        st.subheader("Market Order Distribution")
        price_vol_chart = create_price_volume_chart(sell_data)
        st.plotly_chart(price_vol_chart, use_container_width=True)

        st.divider()

        st.subheader("Price History")
        history_chart = create_history_chart(sell_data['type_id'].iloc[0])
        if history_chart:
            st.plotly_chart(history_chart, use_container_width=False)

            colh1, colh2 = st.columns(2)
            with colh1:
                # Display history data
                st.subheader("History Data")
                history_df = get_market_history(sell_data['type_id'].iloc[0])
                history_df.date = pd.to_datetime(history_df.date).dt.strftime("%Y-%m-%d")
                history_df.average = round(history_df.average.astype(float), 2)
                history_df = history_df.sort_values(by='date', ascending=False)
                history_df.volume = history_df.volume.astype(int)
                st.dataframe(history_df, hide_index=True)

            with colh2:
                avgpr30 = history_df[:30].average.mean()
                avgvol30 = history_df[:30].volume.mean()
                st.subheader(f"{sell_data['type_name'].iloc[0]}",divider=True)
                st.metric("Average Price (30 days)", f"{avgpr30:,.2f} ISK")
                st.metric("Average Volume (30 days)", f"{avgvol30:,.0f}")
        else:
            st.write("History data not available for this item or no item selected")

        st.divider()

        st.subheader("Fitting Data")
        if len(selected_items) == 1:
            if isship:
                st.dataframe(fit_df, hide_index=True)
            else:
                st.write("Fitting data only available for ships")
        else:
            st.write("Fitting data not available for this item or no item selected")

    else:
        st.warning("No data found for the selected filters.")


    # Display sync status in sidebar
    with st.sidebar:
        display_sync_status()


if __name__ == "__main__":
    main()
