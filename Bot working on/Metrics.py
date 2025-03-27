import os
import datetime
import time
import statistics

# ✅ Metrics Storage Path
METRICS_FILE = "chatbot_metrics.tex"

# ✅ Session Tracking
session_started = False  # Track whether the session table has been started
session_start_time = time.time()  # Track session start time

# ✅ Metrics Data Structure
metrics_data = {
    "response_times": [],
    "throughput": [],
    "latency": [],
    "intent_accuracy": [],
    "entity_accuracy": [],
    "error_rate": [],
    "self_learning_rate": []
}


# ✅ Metrics Counters
interaction_count = 0
resolved_count = 0
escalated_count = 0
error_count = 0


# ✅ Utility Function: Record Response Time
def record_response_time(start_time):
    response_time = time.time() - start_time
    if response_time > 0:
        metrics_data["response_times"].append(response_time)


# ✅ Utility Function: Record Latency
def record_latency(latency):
    if latency >= 0:
        metrics_data["latency"].append(latency)


# ✅ Utility Function: Record Interaction Outcome
def record_interaction(outcome):
    global interaction_count, resolved_count, escalated_count, error_count
    interaction_count += 1
    if outcome == "resolved":
        resolved_count += 1
    elif outcome == "escalated":
        escalated_count += 1
    elif outcome == "error":
        error_count += 1


# ✅ Utility Function: Record Accuracy
def record_accuracy(intent_accuracy, entity_accuracy):
    if 0 <= intent_accuracy <= 100:
        metrics_data["intent_accuracy"].append(intent_accuracy)
    if 0 <= entity_accuracy <= 100:
        metrics_data["entity_accuracy"].append(entity_accuracy)


# ✅ Utility Function: Record Learning
def record_learning(self_learning_rate):
    if 0 <= self_learning_rate <= 100:
        metrics_data["self_learning_rate"].append(self_learning_rate)


# ✅ Utility Function: Calculate Metrics Averages
def calculate_metrics():
    global session_start_time

    if interaction_count == 0:
        return None

    # ✅ Correct Throughput Calculation: Queries Processed Per Minute
    total_session_time = time.time() - session_start_time  # Total session duration
    throughput = round((interaction_count / total_session_time) * 60) if total_session_time > 0 else 0

    return {
        "response_time_avg": round(statistics.mean(metrics_data["response_times"]), 3) if metrics_data["response_times"] else 0,
        "throughput_avg": throughput,  # ✅ Now correctly tracks queries per minute
        "latency_avg": round(statistics.mean(metrics_data["latency"]), 3) if metrics_data["latency"] else 0,
        "resolved_percentage": round((resolved_count / interaction_count) * 100, 2) if interaction_count else 0,
        "unanswered_percentage": round((escalated_count / interaction_count) * 100, 2) if interaction_count else 0,
        "intent_accuracy_avg": round(statistics.mean(metrics_data["intent_accuracy"]), 2) if metrics_data["intent_accuracy"] else 0,
        "entity_accuracy_avg": round(statistics.mean(metrics_data["entity_accuracy"]), 2) if metrics_data["entity_accuracy"] else 0,
        "error_rate": round((error_count / interaction_count) * 100, 2) if interaction_count else 0,
        "self_learning_rate_avg": round(statistics.mean(metrics_data["self_learning_rate"]), 2) if metrics_data["self_learning_rate"] else 0
    }


# ✅ Utility Function: Start a New Table for Each Session
def start_session_table():
    global session_started
    if not session_started:
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        # Ensure File Directory Exists
        if os.path.dirname(METRICS_FILE):
            os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)

        with open(METRICS_FILE, "a") as f:
            f.write("\\begin{table}[h!]\n")
            f.write("\\centering\n")
            f.write("\\caption{Chatbot Performance - Session Started: " + date_str + " " + time_str + "}\n")
            f.write("\\begin{tabular}{|l|c|}\n")
            f.write("\\hline\n")
            f.write("\\textbf{Performance Indicator} & \\textbf{Result} \\\\\n")
            f.write("\\hline\n")

        session_started = True


# ✅ Utility Function: Save Metrics to LaTeX File
def save_metrics_to_latex():
    metrics = calculate_metrics()
    if not metrics:
        return

    # Ensure the table header is created at the start of the session
    start_session_table()

    # Append metrics within the same session table
    with open(METRICS_FILE, "a") as f:
        f.write("Average Response Time & {}s \\\\\n".format(metrics["response_time_avg"]))
        f.write("Queries Processed Per Minute & {} \\\\\n".format(metrics["throughput_avg"]))  # ✅ Fixed calculation
        f.write("Processing Delay & {}s \\\\\n".format(metrics["latency_avg"]))
        f.write("Successfully Answered & {}\\% \\\\\n".format(metrics["resolved_percentage"]))
        f.write("Unable to Answer & {}\\% \\\\\n".format(metrics["unanswered_percentage"]))
        f.write("Intent Detection Accuracy & {}\\% \\\\\n".format(metrics["intent_accuracy_avg"]))
        f.write("Keyword Recognition Accuracy & {}\\% \\\\\n".format(metrics["entity_accuracy_avg"]))
        f.write("Errors & {}\\% \\\\\n".format(metrics["error_rate"]))
        f.write("Self-Improvement & {}\\% \\\\\n".format(metrics["self_learning_rate_avg"]))
        f.write("\\hline\n")


# ✅ Utility Function: End the Session Table
def end_session_table():
    global session_started
    if session_started:
        with open(METRICS_FILE, "a") as f:
            f.write("\\end{tabular}\n")
            f.write("\\end{table}\n\n")
        session_started = False

def record_throughput():
    global interaction_count, session_start_time
    elapsed_time = time.time() - session_start_time  # Total session duration
    if elapsed_time > 0:
        throughput = round((interaction_count / elapsed_time) * 60)  # Queries per minute
        metrics_data["throughput"].append(throughput)


# ✅ Utility Function: Record All Interaction Metrics
def record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, self_learning_rate):
    global interaction_count
    if end_time <= start_time:
        print("⚠️ Invalid time range: end_time must be greater than start_time")
        return

    if not (0 <= intent_accuracy <= 100 and 0 <= entity_accuracy <= 100 and 0 <= self_learning_rate <= 100):
        print("⚠️ Accuracy or learning values are out of range (0-100%)")
        return

    interaction_count += 1  # ✅ Increment query count
    record_response_time(start_time)
    record_throughput()  # ✅ Update throughput based on total interactions
    record_latency(latency)
    record_interaction(outcome)
    record_accuracy(intent_accuracy, entity_accuracy)
    record_learning(self_learning_rate)



# ✅ Save Metrics at the End of Session
def save_final_metrics():
    save_metrics_to_latex()
    end_session_table()
