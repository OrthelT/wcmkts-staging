import streamlit as st

from sqlalchemy import text
import pandas as pd
import plotly.express as px
from sqlalchemy.orm import Session
from db_handler import get_update_time
from logging_config import setup_logging
from config import DatabaseConfig
# Insert centralized logging configuration
logger = setup_logging(__name__)

# Import from the root directory

mktdb = DatabaseConfig("wcmkt3")

def get_filter_options(selected_categories=None):
    try:
        # Get data from marketstats table
        query = """
        SELECT DISTINCT type_id, type_name, category_id, category_name, group_id, group_name
        FROM marketstats
        """

        with Session(mktdb.engine) as session:
            result = session.execute(text(query))
            df = pd.DataFrame(result.fetchall(),
                            columns=['type_id', 'type_name', 'category_id', 'category_name', 'group_id', 'group_name'])

            if df.empty:
                return [], []

            categories = sorted(df['category_name'].unique())

            if selected_categories:
                df = df[df['category_name'].isin(selected_categories)]

            items = sorted(df['type_name'].unique())
            logger.info(f"items: {len(items)}")
            logger.info(f"categories: {len(categories)}")

            return categories, items


    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return [], []

def get_market_stats(selected_categories=None, selected_items=None, max_days_remaining=None, doctrine_only=False):
    # Start with base query for marketstats
    query = """
    SELECT ms.*,
           CASE WHEN d.type_id IS NOT NULL THEN 1 ELSE 0 END as is_doctrine,
           d.ship_name,
           d.fits_on_mkt
    FROM marketstats ms
    LEFT JOIN doctrines d ON ms.type_id = d.type_id
    """

    # Get market stats data
    engine = mktdb.engine
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    # Apply filters
    if selected_categories:
        df = df[df['category_name'].isin(selected_categories)]

    if selected_items:
        df = df[df['type_name'].isin(selected_items)]

    if doctrine_only:
        df = df[df['is_doctrine'] == 1]

    # Apply days_remaining filter
    if max_days_remaining is not None:
        df = df[df['days_remaining'] <= max_days_remaining]

    # Group by item and aggregate ship information
    if not df.empty:
        # Create a list of ships for each item
        ship_groups = df.groupby('type_id', group_keys=False).apply(
            lambda x: [f"{row['ship_name']} ({int(row['fits_on_mkt'])})"
                      for _, row in x.iterrows()
                      if pd.notna(row['ship_name'])], include_groups = False
        ).to_dict()

        # Keep only one row per item
        df = df.drop_duplicates(subset=['type_id'])

        # Add the ships column
        df['ships'] = df['type_id'].map(ship_groups)

    return df

def create_days_remaining_chart(df):
    # Create bar chart for days remaining
    fig = px.bar(
        df,
        x='type_name',
        y='days_remaining',
        title='Days of Stock Remaining',
        labels={
            'days_remaining': 'Days Remaining',
            'type_name': 'Item'
        },
        color='category_name',
        color_discrete_sequence=px.colors.qualitative.Set3
    )

    # Update layout for better readability
    fig.update_layout(
        xaxis_title="Item",
        yaxis_title="Days Remaining",
        xaxis={'tickangle': 45},
        height=500
    )

    # Add a horizontal line at days_remaining = 3
    fig.add_hline(y=3, line_dash="dash", line_color="red", annotation_text="Critical Level (3 days)")

    return fig

def main():
       # Title
    st.title("Winter Coalition Market Low Stock Alert")
    st.markdown("""
    This page shows items that are running low on the market. The **Days Remaining** column shows how many days of sales
    can be sustained by the current stock based on historical average sales. Items with fewer days remaining need attention. The **Used In Fits** column
    shows the doctrine ships that use the item (if any) and the number of fits that the current market stock of the item can support.
    """)

    # Sidebar filters
    st.sidebar.header("Filters")
    st.sidebar.markdown("Use the filters below to customize your view of low stock items.")

    # Doctrine items filter
    doctrine_only = st.sidebar.checkbox("Show Doctrine Items Only", value=False, help="Show only items that are used in a doctrine fit, the fits used are shown in the 'Used In Fits' column")

    # Get initial categories
    categories, _ = get_filter_options()

    # Initialize session state for categories if not already present
    if 'selected_categories' not in st.session_state:
        st.session_state.selected_categories = []

    # Category filter - multiselect with checkboxes
    st.sidebar.subheader("Category Filter")
    selected_categories = st.sidebar.multiselect(
        "Select Categories",
        options=categories,
        default=st.session_state.selected_categories,
        help="Select one or more categories to filter the data"
    )

    # Update session state
    st.session_state.selected_categories = selected_categories

    # Days remaining filter
    st.sidebar.subheader("Days Remaining Filter")
    max_days_remaining = st.sidebar.slider(
        "Maximum Days Remaining",
        min_value=0.0,
        max_value=30.0,
        value=7.0,
        step=0.5,
        help="Show only items with days remaining less than or equal to this value"
    )

    # Get filtered data
    df = get_market_stats(selected_categories, None, max_days_remaining, doctrine_only)

    if not df.empty:
        # Sort by days_remaining (ascending) to show most critical items first
        df = df.sort_values('days_remaining')

        # Display metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            critical_items = len(df[df['days_remaining'] <= 3])
            st.metric("Critical Items (≤3 days)", critical_items)
        with col2:
            low_items = len(df[(df['days_remaining'] > 3) & (df['days_remaining'] <= 7)])
            st.metric("Low Stock Items (3-7 days)", low_items)
        with col3:
            total_items = len(df)
            st.metric("Total Filtered Items", total_items)

        st.divider()

        # Format the DataFrame for display
        display_df = df.copy()
        display_df = display_df.drop(columns=['min_price', 'avg_price', 'category_id', 'group_id'])

        # Select and rename columns
        columns_to_show = ['type_id', 'type_name', 'price', 'days_remaining', 'total_volume_remain', 'avg_volume', 'category_name', 'group_name', 'ships']
        display_df = display_df[columns_to_show]

        numeric_formats = {
            'total_volume_remain': st.column_config.NumberColumn('Volume Remaining',  format='localized'),
            'price': st.column_config.NumberColumn('Price', format='localized'),
            'days_remaining': st.column_config.NumberColumn('Days Remaining', format='localized'),
            'avg_volume': st.column_config.NumberColumn('Avg Vol', format='localized'),
        }
        # Rename columns
        column_renames = {
            'type_name': 'Item',
            'group_name': 'Group',
            'category_name': 'Category',
            'ships': 'Used In Fits'
        }
        display_df = display_df.rename(columns=column_renames)

        # Reorder columns
        column_order = ['Item', 'days_remaining', 'price', 'total_volume_remain', 'avg_volume', 'Used In Fits', 'Category', 'Group']
        display_df = display_df[column_order]

        # Add a color indicator for critical items
        def highlight_critical(val):
            try:
                val = float(val)
                if val <= 3:
                    return 'background-color: #fc4103'  # Light red for critical
                elif val <= 7:
                    return 'background-color: #c76d14'  # Light yellow for low
                else:
                    return ''
            except:
                return ''

        # Add a color indicator for doctrine items
        def highlight_doctrine(row):
            # Check if the "Used In Fits" column has data
            try:
                # Check if the value is not empty and not NaN
                if isinstance(row['Used In Fits'], list) and len(row['Used In Fits']) > 0:
                    # Create a list of empty strings for all columns
                    styles = [''] * len(row)
                    # Apply highlighting only to the "Item" column (index 0)
                    styles[0] = 'background-color: #328fed'
                    return styles
            except:
                pass
            return [''] * len(row)

        # Apply the styling - updated from applymap to map
        styled_df = display_df.style.map(highlight_critical, subset=['days_remaining'])

        # Add doctrine highlighting
        styled_df = styled_df.apply(highlight_doctrine, axis=1)

        # Display the dataframe
        st.subheader("Low Stock Items")
        st.dataframe(styled_df, hide_index=True, column_config=numeric_formats)

        # Display charts
        st.subheader("Days Remaining by Item")
        days_chart = create_days_remaining_chart(df)
        st.plotly_chart(days_chart, use_container_width=True)

    else:
        st.warning("No items found with the selected filters.")

    # Display last update timestamp
    st.sidebar.markdown("---")
    st.sidebar.write(f"Last ESI update: {get_update_time()}")

if __name__ == "__main__":
    main()
