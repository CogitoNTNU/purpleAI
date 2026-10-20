# Simple script to run the PurpleAI dashboard
echo "Starting PurpleAI Dashboard..."
echo ""
echo "The dashboard will open in your browser at:"
echo "  - Local:   http://localhost:8501"
echo "  - Network: http://192.168.0.110:8501"
echo ""
echo "Press Ctrl+C to stop the dashboard"
echo ""

# Run Streamlit with network access using uv
uv run streamlit run dashboard.py --server.address 0.0.0.0
