"""Responsive charts with explicit units, UTC axes and stable state colors."""

import altair as alt

STATUS_SCALE = alt.Scale(
    domain=["Allowed", "Blocked", "Classifier error"],
    range=["#60a5fa", "#fb7185", "#fbbf24"],
)
LABELS = {"allowed": "Allowed", "blocked": "Blocked", "error": "Classifier error"}


def traffic_chart(data, share=False):
    data = data.assign(
        utc=data.bucket.dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
        decision=data.status.map(LABELS),
    )
    base = alt.Chart(data)
    chart = base.mark_bar() if share else base.mark_line(strokeWidth=2.5)
    if share:
        chart = chart.encode(x2="bucket_end:T")
    return chart.encode(
        x=alt.X(
            "bucket:T",
            title="Time (UTC)",
            scale=alt.Scale(type="utc"),
            axis=alt.Axis(format="%H:%M", labelOverlap=True, tickCount=6),
        ),
        y=alt.Y(
            "requests:Q",
            title="Share of recorded decisions" if share else "Requests / interval",
            stack="normalize" if share else None,
            axis=alt.Axis(format="%" if share else ",.0f", tickMinStep=1),
            scale=alt.Scale(zero=True),
        ),
        color=alt.Color(
            "decision:N",
            scale=STATUS_SCALE,
            title=None,
            legend=alt.Legend(orient="top", direction="horizontal"),
        ),
        order=alt.Order("decision:N"),
        tooltip=[alt.Tooltip("utc:N", title="Time"), "decision:N", "requests:Q"],
    ).properties(height=240)


def heatmap_chart(data):
    data = data.assign(decision=data.status.map(LABELS))
    selection = alt.selection_point(
        name="endpoint", fields=["path"], toggle=False, clear="dblclick"
    )
    base = alt.Chart(
        data.assign(total=data.path.map(data.groupby("path").requests.sum()))
    ).encode(
        x=alt.X(
            "decision:N",
            title=None,
            sort=["Allowed", "Blocked", "Classifier error"],
            axis=alt.Axis(orient="top", labelAngle=0, labelLimit=150),
        ),
        y=alt.Y(
            "path:N",
            title=None,
            sort=alt.SortField("total", order="descending"),
            axis=alt.Axis(labelLimit=240),
        ),
        tooltip=["path:N", "decision:N", "requests:Q"],
    )
    # Store route totals on each cell so sorting uses total requests, not a single decision.
    cells = base.mark_rect(cornerRadius=3).encode(
        color=alt.Color(
            "requests:Q",
            scale=alt.Scale(scheme="purples", type="sqrt", zero=True),
            legend=None,
        ),
        opacity=alt.condition(selection, alt.value(1), alt.value(0.35)),
    )
    labels = base.mark_text(fontSize=12).encode(
        text=alt.Text("requests:Q", format=","),
        color=alt.condition(
            alt.datum.requests > max(1, data.requests.max() * 0.35),
            alt.value("#ffffff"),
            alt.value("#252136"),
        ),
    )
    return (
        (cells + labels)
        .add_params(selection)
        .properties(height=max(150, data.path.nunique() * 34))
    )


def execution_chart(data, start, end, lanes=None):
    data = data.assign(start_utc=data.start.dt.strftime("%Y-%m-%d %H:%M:%S UTC"))
    selection = alt.selection_point(
        name="execution_pick", fields=["execution"], toggle=False
    )
    base = alt.Chart(data).encode(
        x=alt.X(
            "plot_start:T",
            title="Time (UTC)",
            scale=alt.Scale(type="utc", domain=[start, end]),
            axis=alt.Axis(format="%H:%M", labelOverlap=True, tickCount=6),
        ),
        y=alt.Y(
            "label:N",
            title=None,
            sort=lanes or alt.SortField("plot_start", order="descending"),
            axis=alt.Axis(labelLimit=310),
        ),
        color=alt.Color(
            "result:N",
            title=None,
            legend=None,
            scale=alt.Scale(
                domain=[
                    "Completed",
                    "Error",
                    "Timed out",
                    "Cancelled",
                    "No end event",
                    "Start missing",
                    "Unknown",
                ],
                range=[
                    "#f87171",
                    "#fbbf24",
                    "#fb923c",
                    "#94a3b8",
                    "#c4b5fd",
                    "#94a3b8",
                    "#94a3b8",
                ],
            ),
        ),
        tooltip=[
            "tool:N",
            "result:N",
            "target:N",
            alt.Tooltip("start_utc:N", title="Started"),
            "duration_ms:Q",
            "exit_code:Q",
        ],
    )
    bars = base.mark_bar(size=12, cornerRadius=3).encode(x2="plot_end:T")
    points = base.mark_point(filled=True, size=75).encode(
        shape=alt.condition(
            alt.datum.result == "No end event",
            alt.value("diamond"),
            alt.value("circle"),
        )
    )
    return (bars + points).add_params(selection)


def defense_timeline(data, start, end, lanes=None):
    data = data.assign(
        utc=data.bucket.dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
        decision=data.status.map(LABELS),
    )
    return (
        alt.Chart(
            data[data.requests > 0].assign(
                label=lambda rows: "Defender · " + rows.decision
            )
        )
        .mark_circle(size=45)
        .encode(
            x=alt.X(
                "bucket:T",
                title="Time (UTC)",
                scale=alt.Scale(type="utc", domain=[start, end]),
                axis=alt.Axis(format="%H:%M"),
            ),
            y=alt.Y(
                "label:N",
                title=None,
                sort=lanes
                or [
                    "Defender · Allowed",
                    "Defender · Blocked",
                    "Defender · Classifier error",
                ],
            ),
            color=alt.Color("decision:N", scale=STATUS_SCALE, legend=None),
            tooltip=[alt.Tooltip("utc:N", title="Time"), "decision:N", "requests:Q"],
        )
    )
