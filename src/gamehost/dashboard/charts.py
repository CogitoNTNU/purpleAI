"""Consistent interactive charts for the operational dashboard."""

import altair as alt

STATUS_SCALE = alt.Scale(
    domain=["allowed", "blocked", "error"], range=["#60a5fa", "#fb7185", "#fbbf24"]
)


def traffic_chart(data):
    data = data.assign(utc=data.bucket.dt.strftime("%Y-%m-%d %H:%M UTC"))
    return (
        alt.Chart(data)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "bucket:T",
                title="Time (UTC)",
                scale=alt.Scale(type="utc"),
                axis=alt.Axis(format="%H:%M"),
            ),
            y=alt.Y(
                "requests:Q",
                title="Requests / interval",
                scale=alt.Scale(zero=True),
                axis=alt.Axis(tickMinStep=1),
            ),
            color=alt.Color("status:N", scale=STATUS_SCALE, title="Decision"),
            tooltip=[
                alt.Tooltip("utc:N", title="Time"),
                "status:N",
                "requests:Q",
            ],
        )
        .properties(height=240)
    )


def heatmap_chart(data):
    selection = alt.selection_point(name="endpoint", fields=["path"], toggle=False)
    return (
        alt.Chart(data)
        .mark_rect(cornerRadius=3)
        .encode(
            x=alt.X("status:N", title=None, sort=["allowed", "blocked", "error"]),
            y=alt.Y(
                "path:N",
                title=None,
                sort=alt.SortField("requests", order="descending"),
                axis=alt.Axis(labelLimit=200),
            ),
            color=alt.Color(
                "requests:Q", scale=alt.Scale(scheme="purples"), title="Requests"
            ),
            opacity=alt.condition(selection, alt.value(1), alt.value(0.35)),
            tooltip=["path:N", "status:N", "requests:Q"],
        )
        .add_params(selection)
        .properties(height=max(180, min(480, data.path.nunique() * 30)))
    )


def execution_chart(data, start, end):
    data = data.assign(start_utc=data.start.dt.strftime("%Y-%m-%d %H:%M:%S UTC"))
    selection = alt.selection_point(
        name="execution_pick", fields=["execution"], toggle=False
    )
    base = alt.Chart(data).encode(
        x=alt.X(
            "plot_start:T",
            title="Time (UTC)",
            scale=alt.Scale(type="utc", domain=[start, end]),
            axis=alt.Axis(format="%H:%M:%S"),
        ),
        y=alt.Y(
            "lane:N",
            title=None,
            sort=alt.SortField("plot_start"),
            axis=alt.Axis(labelLimit=230),
        ),
        color=alt.Color(
            "status:N",
            title="Execution result",
            legend=None,
            scale=alt.Scale(
                domain=[
                    "completed",
                    "error",
                    "timeout",
                    "cancelled",
                    "No result logged",
                ],
                range=["#f87171", "#fbbf24", "#fb923c", "#94a3b8", "#c4b5fd"],
            ),
        ),
        tooltip=[
            "tool:N",
            "status:N",
            "target:N",
            "task_id:N",
            alt.Tooltip("start_utc:N", title="Started"),
            "duration_ms:Q",
            "exit_code:Q",
        ],
    )
    # Points keep zero-duration and result-only records clickable.
    bars = base.mark_bar(size=12, cornerRadius=3).encode(x2="plot_end:T")
    points = base.mark_point(filled=True, size=65)
    return (bars + points).add_params(selection)


def defense_timeline(data, start, end):
    data = data.assign(utc=data.bucket.dt.strftime("%Y-%m-%d %H:%M UTC"))
    return (
        alt.Chart(
            data[data.requests > 0].assign(
                lane=lambda rows: "Defender · " + rows.status
            )
        )
        .mark_circle()
        .encode(
            x=alt.X(
                "bucket:T",
                title="Time (UTC)",
                scale=alt.Scale(type="utc", domain=[start, end]),
                axis=alt.Axis(format="%H:%M:%S"),
            ),
            y=alt.Y("lane:N", title=None),
            color=alt.Color("status:N", scale=STATUS_SCALE, legend=None),
            size=alt.Size(
                "requests:Q",
                title="Requests",
                scale=alt.Scale(range=[20, 220]),
                legend=alt.Legend(symbolFillColor="#94a3b8"),
            ),
            tooltip=[
                alt.Tooltip("utc:N", title="Time"),
                "status:N",
                "requests:Q",
            ],
        )
    )
