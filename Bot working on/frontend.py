import streamlit as st
import base64
from app import generate_response, feedback_System


st.set_page_config(page_title="UI/UX Mentor", page_icon="🎨", layout="wide")

# ✅ Custom CSS for Improved UI
st.markdown("""
    <style>
        body {
            background-color: #121212;
            color: #E0E0E0;
        }
        .stChatMessage {
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .stChatMessage.user {
            background-color: #1E1E1E;
            text-align: right;
        }
        .stChatMessage.assistant {
            background-color: #2A2A2A;
            border-left: 4px solid #64B5F6;
        }
        .stTextArea textarea {
            border-radius: 8px;
            padding: 10px;
            font-size: 16px;
        }
        .stButton button {
            background: linear-gradient(90deg, #64B5F6, #42A5F5);
            border-radius: 8px;
            color: black;
            font-weight: bold;
        }
        .stButton button:hover {
            background: linear-gradient(90deg, #e371ff, #1E88E5);
            color: black;
            font-weight: bold;
        }
        .feedback-btn {
            margin-top: 5px;
        }
    </style>
""", unsafe_allow_html=True)

# ✅ Initialize session state
if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "learning_mode" not in st.session_state:
    st.session_state["learning_mode"] = False

if "current_topic" not in st.session_state:
    st.session_state["current_topic"] = None

if "challenge_mode" not in st.session_state:
    st.session_state["challenge_mode"] = False

if "current_challenge" not in st.session_state:
    st.session_state["current_challenge"] = None

if "paused_learning" not in st.session_state:
    st.session_state["paused_learning"] = False


def decode_base64_image(image_base64):
    """Decode base64-encoded image, handling common prefixes."""
    if not image_base64:
        return None
    try:
        
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
        return base64.b64decode(image_base64)
    except Exception as e:
        st.error(f"⚠️ Error decoding image: {str(e)}")
        return None


st.title("🎨 UI/UX Mentor")
st.subheader("Your Personal Guide to Design Excellence")
st.write("Click on learning or challenge yourself to test your knowledge!")


def show_feedback_form(index, user_input, response):
    """Show a feedback form when thumbs-down is clicked."""
    with st.form(key=f"feedback_form_{index}"):
        st.write("📝 Provide Feedback")
        user_comments = st.text_area("What can be improved? (Required, min 10 characters)", max_chars=300)
        user_suggestion = st.text_area("Any suggestions for improvement? (Optional)", max_chars=300)
        submit_button = st.form_submit_button("Submit Feedback")

        if submit_button:
            if len(user_comments.strip()) < 10:
                st.warning("⚠️ Feedback comment must be at least 10 characters.")
            else:
                feedback_System(user_input, response, feedback_type="thumbs_down", user_comments=user_comments, user_suggestion=user_suggestion)
                st.success("✅ Feedback submitted. Thank you!")
                st.session_state[f"feedback_given_{index}"] = True
                st.rerun()

for index, message in enumerate(st.session_state["messages"]):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("image"):
            image_data = decode_base64_image(message["image"])
            if image_data:
                st.image(image_data, caption="📐 Generated Wireframe", width=600)

        if message["role"] == "assistant":
            if not st.session_state.get(f"feedback_given_{index}", False):
                col1, col2 = st.columns([0.5, 0.5])
                with col1:
                    if st.button("👍", key=f"thumbs_up_{index}", help="Helpful response"):
                        feedback_System(st.session_state["messages"][index - 1]["content"], message["content"], feedback_type="thumbs_up")
                        st.success("✅ Thanks for your feedback!")
                        st.session_state[f"feedback_given_{index}"] = True
                        st.rerun()

                with col2:
                    if st.button("👎", key=f"thumbs_down_{index}", help="Needs improvement"):
                        st.session_state[f"show_feedback_form_{index}"] = True
                        st.rerun()

            if st.session_state.get(f"show_feedback_form_{index}", False):
                show_feedback_form(index, st.session_state["messages"][index - 1]["content"], message["content"])

        if (
            st.session_state["learning_mode"]
            and message["role"] == "assistant"
            and index == len(st.session_state["messages"]) - 1  # Latest response only
        ):
            if st.button("⏸ Take a Break from Learning", key="pause_learning"):
                st.session_state["paused_learning"] = True
                st.session_state["learning_mode"] = False
                st.session_state["current_topic"] = None
                st.success("✅ You have paused learning mode. Feel free to ask any question!")
                st.rerun()

#Start UI/UX Learning & UI/UX Challenge
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    if not st.session_state["learning_mode"] and not st.session_state["paused_learning"]:
        if st.button("🎓 Start UI/UX Learning", key="start_learning", help="Learn UI/UX design step by step with the AI!"):
            st.session_state["learning_mode"] = True
            st.session_state["current_topic"] = None
            st.rerun()

    # ✅ Resume Learning button if paused
    if st.session_state["paused_learning"]:
        if st.button("▶️ Resume Learning", key="resume_learning"):
            st.session_state["learning_mode"] = True
            st.session_state["paused_learning"] = False
            st.success("✅ Resumed learning mode. Let's continue!")
            st.rerun()

with col2:
    if not st.session_state["challenge_mode"]:
        if st.button("🎯 Start UI/UX Challenge", key="start_challenge", help="Test your UI/UX knowledge with real-world problem-solving!"):
            st.session_state["challenge_mode"] = True
            st.session_state["current_challenge"] = None
            st.rerun()

if st.session_state["learning_mode"] and st.session_state["current_topic"] is None:
    with st.spinner("Generating learning topic..."):
        learning_intro = generate_response("Introduce the user to UI/UX learning and ask which topic they'd like to start with.")
        st.session_state["current_topic"] = learning_intro["text"]
    st.session_state["messages"].append({"role": "assistant", "content": st.session_state["current_topic"]})
    st.rerun()

if st.session_state["challenge_mode"] and st.session_state["current_challenge"] is None:
    with st.spinner("Generating UI/UX challenge question..."):
        challenge = generate_response("Generate a UI/UX design challenge that requires practical application.")
        st.session_state["current_challenge"] = challenge["text"]
    st.session_state["messages"].append({"role": "assistant", "content": st.session_state["current_challenge"]})
    st.session_state["challenge_mode"] = False
    st.rerun()

user_input = st.chat_input("Ask your UI/UX question, continue learning, or answer the challenge...")

if user_input:
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    ai_response = None

    if st.session_state["current_challenge"]:
        with st.spinner("Evaluating your response..."):
            ai_response = generate_response(user_input, challenge_mode=True, challenge_question=st.session_state["current_challenge"])
        st.session_state["messages"].append({"role": "assistant", "content": ai_response["text"]})
        st.session_state["current_challenge"] = None

    elif st.session_state["learning_mode"]:
        with st.spinner("Continuing UI/UX learning..."):
            ai_response = generate_response(f"Continue teaching the user about {st.session_state['current_topic']} based on their input: {user_input}")
        st.session_state["messages"].append({"role": "assistant", "content": ai_response["text"]})

    else:
        with st.spinner("Generating response..."):
            ai_response = generate_response(user_input)
        st.session_state["messages"].append({"role": "assistant", "content": ai_response["text"], "image": ai_response.get("image")})

    with st.chat_message("assistant"):
        st.markdown(ai_response["text"])
        if ai_response.get("image"):
            image_data = decode_base64_image(ai_response["image"])
            if image_data:
                st.image(image_data, caption="📐 Generated Wireframe", width=600)

    st.rerun()
