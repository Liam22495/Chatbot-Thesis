import subprocess
import requests
import time
import base64
import re
from io import BytesIO
import logging
import os
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate, AIMessagePromptTemplate
from langchain_core.prompts import ChatPromptTemplate
import firebase_admin
from firebase_admin import credentials, firestore
from Metrics import record_interaction_metrics
import atexit
from Metrics import save_final_metrics

####
logging.info("Initializing Firebase...")
FIREBASE_CREDENTIALS_PATH = r"firebase_service.json"

if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
db = firestore.client()

FEEDBACK_THRESHOLDS = {
    "wireframe_quality": 5,
    "code_accuracy": 7,
    "explanation_clarity": 10,
}

#####
URL = "http://localhost:11434"

def is_ollama_running():
    try:
        response = requests.get(f"{URL}/api/tags", timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False

if not is_ollama_running():
    print("⚡ Ollama seems to not be running, booting up...")
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

model = ChatOllama(model="llama3", base_url=URL)

####
system_message = SystemMessagePromptTemplate.from_template(
    "You are a helpful AI Assistant and mentor specializing in UI/UX design. "
    "Provide clear, structured, and insightful answers to design related questions. "
    "Guide users through UX and UI learning paths, real world case studies, and interactive exercises."
    "Provide follow up questions to the topic to help the user with their next step in learning"
)

chat_history = []

def get_history():
    formatted_history = [system_message]
    for chat in chat_history:
        formatted_history.append(HumanMessagePromptTemplate.from_template(chat["user"]))
        formatted_history.append(AIMessagePromptTemplate.from_template(chat["assistant"]))
    return formatted_history


def feedback_System(user_input, response, feedback_type, user_comments=None, user_suggestion=None):
    """
    Handles feedback collection, stores it in Firebase, and triggers automated fine-tuning when thresholds are met.
    - Automatically fine-tunes when enough negative feedback is collected using Ollama CLI.
    - Reloads the fine-tuned model into Ollama.
    
    Args:
        user_input (str): The user's input.
        response (str): The AI's response.
        feedback_type (str): Type of feedback ("thumbs_up" or "thumbs_down").
        user_comments (str, optional): User's comments on the feedback.
        user_suggestion (str, optional): User's alternative suggestion.
    """
    global model

    # ✅ Metrics setup:
    start_time = time.time()
    latency_start = time.time()
    outcome = "resolved"
    intent_accuracy = 100  # Placeholder since no accuracy measurement is available
    entity_accuracy = 100
    latency = 0
    self_learning_rate = 0

    try:
        if feedback_type == "thumbs_down" and (not user_comments or len(user_comments.strip()) < 10):
            raise ValueError("❗ Feedback comment must be at least 10 characters.")

        feedback_data = {
            "user_input": user_input,
            "response": response,
            "feedback": feedback_type,
            "user_comments": user_comments or "No comments provided.",
            "user_suggestion": user_suggestion or "No suggestion provided.",
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
        db.collection("feedback").add(feedback_data)
        logging.info("✅ Feedback saved successfully!")

        if feedback_type == "thumbs_up":
            logging.info("👍 Positive feedback received. No further action required.")

            # ✅ Metrics recording for positive feedback
            latency = time.time() - latency_start
            end_time = time.time()
            record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, self_learning_rate)

        elif feedback_type == "thumbs_down":
            logging.info("💡 Processing negative feedback for automated fine-tuning...")

            feedback_ref = db.collection("feedback").where("feedback", "==", "thumbs_down").stream()
            fine_tune_data_path = os.path.join("fine_tuned_data", "fine_tune_data.txt")
            count = 0

            os.makedirs("fine_tuned_data", exist_ok=True)
            with open(fine_tune_data_path, "w") as f:
                for doc in feedback_ref:
                    data = doc.to_dict()
                    category = data.get("category", "general")

                    if len(data.get("user_comments", "").strip()) < 10:
                        continue

                    if count >= FEEDBACK_THRESHOLDS.get(category, 10):
                        continue

                    f.write(f"Input: {data.get('user_input', 'N/A')}\n")
                    f.write(f"Response: {data.get('response', 'N/A')}\n")
                    f.write(f"Comment: {data.get('user_comments', 'No comment')}\n")
                    f.write(f"Suggested Response: {data.get('user_suggestion', 'No suggestion')}\n\n")
                    count += 1

            logging.info(f"✅ Processed {count} feedback entries for fine-tuning.")

            if count > 0:
                logging.info("🚀 Starting automated fine-tuning process with Ollama...")

                fine_tune_command = [
                    "ollama", "create", "fine_tuned_model",
                    "--model", "llama3",
                    "--file", fine_tune_data_path
                ]

                try:
                    subprocess.run(fine_tune_command, check=True)
                    logging.info("✅ Fine-tuning completed successfully!")

                    # ✅ Reload Ollama with fine-tuned model
                    logging.info("♻️ Reloading Ollama server with fine-tuned model...")
                    subprocess.run(["ollama", "serve", "--model", "fine_tuned_model"], check=True)

                    logging.info("✅ Fine-tuned model deployed successfully!")

                    # ✅ Self-learning metric update
                    self_learning_rate = 1  # Fine-tuning occurred

                except subprocess.CalledProcessError as e:
                    outcome = "error"
                    logging.error(f"❌ Error during fine-tuning: {e}")

                    latency = time.time() - latency_start
                    end_time = time.time()
                    record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, self_learning_rate)

                    return {"text": "❌ Error during fine-tuning. Please check the server logs."}

        # ✅ Metrics recording
        latency = time.time() - latency_start
        end_time = time.time()
        record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, self_learning_rate)

    except ValueError as ve:
        outcome = "error"
        logging.warning(str(ve))

        latency = time.time() - latency_start
        end_time = time.time()
        record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, self_learning_rate)

    except Exception as e:
        outcome = "error"
        logging.error(f"❌ Error in feedback_System: {e}", exc_info=True)

        latency = time.time() - latency_start
        end_time = time.time()
        record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, self_learning_rate)


def generate_wireframe(ai_response):
    """
    Extracts pages and sections dynamically from AI response using flexible formatting and 
    generates a realistic high-fidelity wireframe with components adapted to section names:
    - Supports **Bold**, numbered, or bulleted page names.
    - Limits each page to a maximum of 8 sections for clarity.
    - Shortens long labels to 5 words or fewer.
    - Optimized layout, spacing, and alignment for better readability.
    - Filters out non-structural lines (e.g., introductions or extra commentary).
    - Fixed page headers to stay visually separate from sections.
    """

    # ✅ Metrics setup:
    start_time = time.time()
    latency_start = time.time()
    outcome = "resolved"
    intent_accuracy = 100  # Placeholder since no accuracy measurement is available
    entity_accuracy = 100
    latency = 0

    try:
        # Page Structure Extraction
        def shorten_label(label, max_words=5):
            """Shorten labels to a maximum number of words (default 5)."""
            return ' '.join(label.split()[:max_words])  # Limit to first 5 words

        page_structure = {}
        current_page = None
        page_pattern = re.compile(r"^\s*(\*\*.+?\*\*|[A-Za-z\s]+):?\s*$")
        section_pattern = re.compile(r"^\s*[-*+\d.]+\s*(.+)")
        ignore_patterns = ["wireframe", "layout", "website", "visual", "design", "based on", "structure", "here is"]

        for line in ai_response.split("\n"):
            line = line.strip()

            if any(keyword in line.lower() for keyword in ignore_patterns):
                continue

            # Detect page titles (flexible formatting)
            if page_pattern.match(line):
                current_page = re.sub(r"\*\*", "", line).strip().replace(":", "")
                if len(current_page) > 2:  # Ensure valid page name
                    page_structure[current_page] = []

            elif section_pattern.match(line) and current_page:
                section = section_pattern.match(line).group(1).strip()
                if len(section) > 3 and len(page_structure[current_page]) < 8:  # Limit to 8 sections per page
                    page_structure[current_page].append(shorten_label(section))

            # Fallback pages
            elif current_page and len(line) > 3 and ":" not in line and len(page_structure[current_page]) < 8:
                page_structure[current_page].append(shorten_label(line))

        print(f"📌 AI-Extracted Page Structure: {page_structure}")

        # Fallback if no structure is found
        if not page_structure:
            print("⚠️ No pages found. Using fallback structure.")
            page_structure = {
                "Homepage": ["Navigation Bar", "Hero Section", "Main Content", "CTA Button", "Footer"],
                "Contact Us": ["Contact Form", "Map Section", "Social Media Links", "Footer"]
            }

        print(f"⚡ Wireframe generation triggered for pages: {list(page_structure.keys())}")

        # Setup canvas
        fig, axes = plt.subplots(len(page_structure), 1, figsize=(10, 12 * len(page_structure)), facecolor='white')
        if len(page_structure) == 1:
            axes = [axes]

        section_colours = ['#E3F2FD', '#FFEBEE', '#E8F5E9', '#FFF3E0', '#EDE7F6', '#F3E5F5']
        header_colour = '#1565C0'
        border_colour = '#333333'

        # Component Detection
        def draw_component(ax, section_name, y_position, section_height, colour_index):
            colour = section_colours[colour_index % len(section_colours)]

            # Navigation Bar
            if any(keyword in section_name.lower() for keyword in ["navigation bar", "menu", "navbar"]):
                nav_items = ["Home", "About", "Portfolio", "Contact"]
                ax.add_patch(Rectangle((1, y_position), 10, 0.7, fill=True, color="#90CAF9", edgecolor=border_colour, linewidth=1))
                for idx, item in enumerate(nav_items):
                    ax.text(2 + idx * 2.5, y_position + 0.35, item, ha="center", va="center", fontsize=10, color='black')

            # Button Section (CTA - Only if explicitly requested)
            elif any(keyword in section_name.lower() for keyword in ["cta", "call to action"]):
                ax.add_patch(Rectangle((4, y_position + 0.5), 4, 1, fill=True, color='#FFA726', edgecolor=border_colour, linewidth=1.5))
                ax.text(6, y_position + 1, "Click Here", ha="center", va="center", fontsize=12, color='white')


            # Default Placeholder
            else:
                ax.add_patch(Rectangle((2, y_position), 8, section_height, fill=True, color=colour, edgecolor=border_colour, linewidth=1.5))
                ax.text(6, y_position + section_height / 2, section_name, ha="center", va="center", fontsize=14, weight="bold")

        # Loop through pages and render components
        for ax, (page, sections) in zip(axes, page_structure.items()):
            ax.set_xlim(0, 12)
            ax.set_ylim(0, 20)
            ax.axis('off')

            # Page Header
            ax.add_patch(FancyBboxPatch((0.5, 19), 11, 1, boxstyle="round,pad=0.3", facecolor=header_colour,
                                        edgecolor=border_colour, linewidth=2))
            ax.text(6, 19.5, page, ha="center", va="center", fontsize=20, weight="bold", color='white')

            y_position = 17
            section_height = max(1.8, 14 // (len(sections) + 2))

            for i, section in enumerate(sections):
                draw_component(ax, section, y_position, section_height, i)
                y_position -= section_height + 1.5

        fig.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
        buf.seek(0)
        image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        buf.close()

        # ✅ Metrics recording
        latency = time.time() - latency_start
        end_time = time.time()
        record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, 0)

        return image_base64

    except Exception as e:
        # Handle errors and record metrics
        outcome = "error"
        print(f"❌ Error in generate_wireframe: {str(e)}")

        latency = time.time() - latency_start
        end_time = time.time()
        record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, 0)

        return None
    
def vauge_requests(user_input):
    """
    Determines if the user input is a vague general request that needs UI/UX context.
    Returns True if the input is vague, otherwise False.
    """
    vague_phrases = [
        "tell me something random", "say something interesting", "give me a fact",
        "tell me a fun fact", "surprise me", "say something cool", "tell me a joke",
        "give me something new", "what’s something interesting?"
    ]
    
    # Convert input to lowercase for case-insensitive matching
    user_input_lower = user_input.strip().lower()

    return any(phrase in user_input_lower for phrase in vague_phrases)



def generate_response(user_input, learning_mode=False, learning_topic=None, challenge_mode=False, challenge_question=None):
    """
    Generates AI response, supporting text-only, wireframe generation, and fallback scenarios.
    Uses Llama for wireframe information detection.
    """
    global chat_history, correct_intent_count, total_intent_checks, correct_entity_count, total_entity_checks

    #Metrics setup:
    start_time = time.time()
    latency_start = time.time()
    outcome = "resolved"
    latency = 0
    total_intent_checks = 0
    correct_intent_count = 0
    intent_accuracy = 0
    total_entity_checks = 0
    correct_entity_count = 0

    def detect_wireframe_intent(user_input, learning_mode=False):
        """Uses Llama to detect if the user requests a wireframe or just an explanation."""
        prompt = f"""
        Classify the following user input into one of the following intents:
        - 'wireframe_request' if the user explicitly asks to generate a wireframe, visual layout, or website structure image.
        - 'followup_wireframe_request' if the user references a previously provided setup or explanation and now requests a wireframe.
        - 'explanation_request' if the user asks how to create, design, or learn about wireframes.
        - 'setup_request' if the user asks for a textual website setup or list of sections without requesting a wireframe.
        - 'general_request' for any other input.

        Important: 
        - If the user is in **learning mode**, do not classify any input as 'wireframe_request' or 'followup_wireframe_request' unless explicitly stated.
        - Only classify as 'wireframe_request' or 'followup_wireframe_request' if the input clearly mentions visual generation or wireframe creation.
        - If the user says to tell them something random, state a fun fact about UI/UX design
        
        Examples:
        - "Generate a wireframe for a perfume website" → wireframe_request
        - "Based on the setup you provided, generate a wireframe" → followup_wireframe_request
        - "How do I create a wireframe" → explanation_request
        - "Can you now provide a setup for the perfume website that you think a perfume website should have?" → setup_request
        - "I would add shadow effects and common icons that is known worldwide" → general_request (if learning_mode=True)
        - "Tell me something random" → general_request

        User Input: {user_input}

        Output only the intent (wireframe_request, followup_wireframe_request, explanation_request, setup_request, or general_request).
        """

        if learning_mode:
            prompt += "\n\n**NOTE:** Since the user is in learning mode, avoid classifying input as 'wireframe_request' or 'followup_wireframe_request' unless explicitly requested."

        chat_template = ChatPromptTemplate.from_messages([HumanMessagePromptTemplate.from_template(prompt)])
        chain = chat_template | model | StrOutputParser()
        result = chain.invoke({}).strip().lower()

        return result

    try:
        intent = detect_wireframe_intent(user_input, learning_mode=learning_mode)
        print(f"🧠 Detected Intent: {intent}")

        # ✅ Intent Accuracy Calculation (Inline)
        total_intent_checks += 1
        expected_intent = "general_request"
        if "wireframe" in user_input.lower() or "layout" in user_input.lower() or "structure" in user_input.lower():
            expected_intent = "wireframe_request"
        elif "based on previous" in user_input.lower() or "use the setup" in user_input.lower():
            expected_intent = "followup_wireframe_request"
        elif "how to" in user_input.lower() or "explain" in user_input.lower() or "what is" in user_input.lower():
            expected_intent = "explanation_request"
        elif "setup" in user_input.lower() or "list of sections" in user_input.lower():
            expected_intent = "setup_request"

        # Learning Mode Rule
        if learning_mode and expected_intent in ["wireframe_request", "followup_wireframe_request"]:
            expected_intent = "general_request"

        if intent == expected_intent:
            correct_intent_count += 1
        intent_accuracy = (correct_intent_count / total_intent_checks) * 100 if total_intent_checks > 0 else 0

        # ✅ Learning Mode Response
        if learning_mode:
            learning_prompt = f"""
            The user is in UI/UX learning mode.
            The current learning topic is: {learning_topic}.
            User Input: {user_input}

            Important:
            - The user should explain their design process step-by-step in words, rather than providing an image or prototype.
            - Guide them through structured learning with detailed examples and practical steps.
            - If they have completed this topic, suggest a follow-up learning topic.
            """
            chat_template = ChatPromptTemplate.from_messages([HumanMessagePromptTemplate.from_template(learning_prompt)])
            chain = chat_template | model | StrOutputParser()
            learning_response = chain.invoke({}).strip()

            latency = time.time() - latency_start
            end_time = time.time()
            record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, 0, 0)

            return {"text": learning_response, "image": None}

        # ✅ UI/UX Challenge Response
        if challenge_mode and challenge_question:
            evaluation_prompt = f"""
            The user is participating in a UI/UX challenge.
            Their challenge question: {challenge_question}
            User's response: {user_input}

            **Important:** 
            - **DO NOT ask the user to submit a prototype, wireframe, PDF, PNG, GIF, or any visual design.**
            - **DO NOT mention tools like Figma, Sketch, or Adobe XD.**
            - The user should describe their approach using **text-based, step-by-step explanations**.
            - Guide them to **explain how they would structure the UI/UX design**, detailing the reasoning behind their decisions.
            - Provide constructive feedback, suggest improvements, and ask follow-up questions to refine their thought process.

            **Format your response as follows:**
            - **Step 1:** [Explain what the user should consider first]
            - **Step 2:** [Guide them through the next logical step]
            - **Step 3:** [Continue until a full thought process is outlined]
            - **Feedback:** [Comment on their response and suggest refinements]
            - **Follow-up Question:** [Encourage deeper thinking]
            """
            chat_template = ChatPromptTemplate.from_messages([HumanMessagePromptTemplate.from_template(evaluation_prompt)])
            chain = chat_template | model | StrOutputParser()
            challenge_feedback = chain.invoke({}).strip()

            latency = time.time() - latency_start
            end_time = time.time()
            record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, 0, 0)

            return {"text": challenge_feedback, "image": None}

        if intent == "wireframe_request":
            print(f"🚀 Wireframe request detected! User input: {user_input}")

            wireframe_prompt = f"""
            The user explicitly requested a wireframe.
            Their request: {user_input}

            Instructions:
            - Identify the main pages required for this website.
            - For each page, list realistic sections as they would appear on a modern website.
            - Limit each page to a maximum of 7 sections for clarity.
            - Use concise labels (5 words or fewer).
            - Format the structure as:
              **Page Name**
              - Section 1
              - Section 2
              - Section 3

            Examples:
            **Homepage**
            - Navigation Bar
            - Hero Section
            - Featured Products
            - Testimonials
            - Footer

            **Contact Us**
            - Contact Form
            - Map Section
            - Social Media Links
            - Footer

            Important: Ensure that the structure is visually clear, concise, and aligned with modern design trends.
            """
            chat_template = ChatPromptTemplate.from_messages([HumanMessagePromptTemplate.from_template(wireframe_prompt)])
            chain = chat_template | model | StrOutputParser()
            wireframe_details = chain.invoke({}).strip()

            try:
                # ✅ Entity Accuracy Calculation (Inline)
                expected_entities = re.findall(r'\b\w+\b', user_input.lower())
                response_entities = re.findall(r'\b\w+\b', wireframe_details.lower())

                total_entity_checks += len(expected_entities)
                correct_entity_count += sum(entity in response_entities for entity in expected_entities)
                entity_accuracy = (correct_entity_count / total_entity_checks) * 100 if total_entity_checks > 0 else 0
              
                print(f"📌 AI-Extracted Wireframe Details: {wireframe_details}")

                wireframe_image = generate_wireframe(wireframe_details)

                latency = time.time() - latency_start
                end_time = time.time()
                record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, 0)

                return {"text": "Here is the requested wireframe:", "image": f"data:image/png;base64,{wireframe_image}"}

            except Exception as e:
                outcome = "error"
                print(f"⚠️ Error processing AI response: {str(e)}")

                latency = time.time() - latency_start
                end_time = time.time()
                record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, 0, 0)

                return {"text": f"⚠️ Error processing AI response: {str(e)}", "image": None}

        if intent == "followup_wireframe_request":
            print(f"🔁 Follow-up wireframe request detected! User input: {user_input}")

            # Generate wireframe using previous setup stored in chat history
            last_setup = None
            for message in reversed(chat_history):
                if "**Homepage**" in message["assistant"] or "**Contact Us**" in message["assistant"]:
                    last_setup = message["assistant"]
                    break

            if last_setup:
                try:
                    # ✅ Entity Accuracy Calculation (Inline)
                    expected_entities = re.findall(r'\b\w+\b', user_input.lower())
                    response_entities = re.findall(r'\b\w+\b', last_setup.lower())

                    total_entity_checks += len(expected_entities)
                    correct_entity_count += sum(entity in response_entities for entity in expected_entities)
                    entity_accuracy = (correct_entity_count / total_entity_checks) * 100 if total_entity_checks > 0 else 0

                    print(f"📌 Using previous setup for wireframe: {last_setup}")
                    wireframe_image = generate_wireframe(last_setup)

                    latency = time.time() - latency_start
                    end_time = time.time()
                    record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, 0)

                    return {"text": "Here is the wireframe based on the previous setup:", "image": f"data:image/png;base64,{wireframe_image}"}

                except Exception as e:
                    outcome = "error"
                    print(f"⚠️ Error processing AI response: {str(e)}")

                    latency = time.time() - latency_start
                    end_time = time.time()
                    record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, 0, 0)

                    return {"text": f"⚠️ Error processing AI response: {str(e)}", "image": None}

            else:
                outcome = "error"
                latency = time.time() - latency_start
                end_time = time.time()
                record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, 0, 0)

                return {"text": "⚠️ No previous setup found. Please provide the website structure or request a new wireframe.", "image": None}

        if intent == "explanation_request":
            print(f"💡 Explanation request detected! User input: {user_input}")

            explanation_prompt = f"""
            The user wants an explanation about creating a wireframe.
            Their request: {user_input}

            Instructions:
            - Provide a clear step-by-step guide on creating a wireframe.
            - Tailor the explanation to the website industry if mentioned.
            - Keep the explanation concise, using short paragraphs and bullet points when possible.
            - Offer practical tips and common mistakes to avoid.

            """
            chat_template = ChatPromptTemplate.from_messages([HumanMessagePromptTemplate.from_template(explanation_prompt)])
            chain = chat_template | model | StrOutputParser()
            explanation_response = chain.invoke({}).strip()

            latency = time.time() - latency_start
            end_time = time.time()
            record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, 0, 0)

            return {"text": explanation_response, "image": None}

        if intent == "setup_request":
            print(f"📝 Setup request detected! User input: {user_input}")

            setup_prompt = f"""
            The user wants a textual website setup.
            Their request: {user_input}

            Instructions:
            - Provide a list of key pages and their main sections.
            - Limit each page to a maximum of 7 sections.
            - Use concise labels (5 words or fewer).
            - Avoid generating a wireframe image.

            Examples:
            **Homepage**
            - Navigation Bar
            - Hero Section
            - Featured Products
            - Testimonials
            - Footer

            **Contact Us**
            - Contact Form
            - Map Section
            - Social Media Links
            - Footer
            """
            chat_template = ChatPromptTemplate.from_messages([HumanMessagePromptTemplate.from_template(setup_prompt)])
            chain = chat_template | model | StrOutputParser()
            setup_response = chain.invoke({}).strip()

            expected_entities = re.findall(r'\b\w+\b', user_input.lower())
            response_entities = re.findall(r'\b\w+\b', setup_response.lower())

            total_entity_checks += len(expected_entities)
            correct_entity_count += sum(entity in response_entities for entity in expected_entities)
            entity_accuracy = (correct_entity_count / total_entity_checks) * 100 if total_entity_checks > 0 else 0

            chat_history.append({"user": user_input, "assistant": setup_response})

            latency = time.time() - latency_start
            end_time = time.time()
            record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, 0)

            return {"text": setup_response, "image": None}

        # 🗨️ General Chatbot Responses (Only force UI/UX if query is vague)
        if intent == "general_request":
            if vauge_requests(user_input):
                user_input = f"Provide a UI/UX related fun fact or a joke or tip instead of a random response, only choose one. User request: {user_input}"

        formatted_prompt = HumanMessagePromptTemplate.from_template(user_input)
        conversation = get_history()
        conversation.append(formatted_prompt)


        chat_template = ChatPromptTemplate.from_messages(conversation)
        chain = chat_template | model | StrOutputParser()
        response = chain.invoke({})

        expected_entities = re.findall(r'\b\w+\b', user_input.lower())
        response_entities = re.findall(r'\b\w+\b', response.lower())

        total_entity_checks += len(expected_entities)
        correct_entity_count += sum(entity in response_entities for entity in expected_entities)
        entity_accuracy = (correct_entity_count / total_entity_checks) * 100 if total_entity_checks > 0 else 0

        chat_history.append({"user": user_input, "assistant": response})

        latency = time.time() - latency_start
        end_time = time.time()
        record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, entity_accuracy, 0)

        return {"text": response, "image": None}

    except Exception as e:
        outcome = "error"
        print(f"❌ Error in generate_response: {str(e)}")

        latency = time.time() - latency_start
        end_time = time.time()
        record_interaction_metrics(start_time, end_time, outcome, latency, intent_accuracy, 0, 0)

        return {"text": f"❌ Error: {str(e)}", "image": None}

atexit.register(save_final_metrics)
