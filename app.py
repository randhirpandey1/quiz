from flask import Flask, render_template, request, send_file, redirect, url_for
import fitz  # PyMuPDF
from openai import OpenAI
from fpdf import FPDF
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

app = Flask(__name__)

# Function to extract text from PDF
def pdf_to_text(pdf_path):
    pdf_document = fitz.open(pdf_path)
    all_text = ""
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        page_text = page.get_text()
        all_text += page_text
    return all_text

# Initialize the OpenAI client
client = OpenAI(api_key="key")  # Replace with your actual API key

# Function to call the API
def call_api(prompt):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o-mini",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Failed to call API: {e}")
        return ""

# Function to accumulate and split text
def accumulate_and_split_text(text, max_length=1000):
    accumulated_text = ""
    for line in text.split('\n'):
        accumulated_text += line
        if len(accumulated_text) + len(line) >= max_length:
            yield accumulated_text
            accumulated_text = ""  # Reset for the next block
    if accumulated_text:  # Yield remaining text if any
        yield accumulated_text

# Create a PDF document
class PDF(FPDF):
    def header(self):
        self.set_font('DejaVu', 'B', 12)
        self.cell(0, 10, 'Generated Flashcards', 0, 1, 'C')

    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('DejaVu', 'B', 12)
        self.cell(0, 10, title, 0, 1)
        self.ln(5)

    def chapter_body(self, body):
        self.set_font('DejaVu', '', 12)
        self.multi_cell(0, 10, body)
        self.ln()

# Route for the homepage
@app.route('/')
def index():
    return render_template('index.html')

# Route to handle file upload and processing
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('index'))
    if file:
        file_path = os.path.join('input.pdf')
        file.save(file_path)
        extracted_text = pdf_to_text(file_path)

        pdf = PDF()
        pdf.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
        pdf.add_font('DejaVu', 'B', 'DejaVuSans-Bold.ttf', uni=True)
        pdf.add_font('DejaVu', 'I', 'DejaVuSans-Oblique.ttf', uni=True)

        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        try:
            prompts = []
            for accumulated_text in accumulate_and_split_text(extracted_text):
                prompt_with_instruction = f"I will upload some facts from a book, make all possible questions and answers from that, make questions in MCQ format, think of other options by yourself, similar to the correct one, so the answer can't be just guessed. put all questions together and all answers together .\n{accumulated_text}"
                prompts.append(prompt_with_instruction)

            with ThreadPoolExecutor(max_workers=min(480, os.cpu_count() + 32)) as executor:
                future_to_prompt = {executor.submit(call_api, prompt): prompt for prompt in prompts}
                for future in as_completed(future_to_prompt):
                    prompt = future_to_prompt[future]
                    try:
                        api_response = future.result()
                        pdf.chapter_title("Generated Response:")
                        pdf.chapter_body(api_response)
                    except Exception as exc:
                        print(f"{prompt} generated an exception: {exc}")

            output_pdf_path = './output.pdf'
            pdf.output(output_pdf_path)

            return send_file(output_pdf_path, as_attachment=True)
        except FileNotFoundError:
            return "Input file not found.", 404

if __name__ == '__main__':
    app.run(debug=True)
