# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port the app runs on
EXPOSE 7000

# Set environment variables
ENV FLASK_APP=location.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV PORT=7000

# Run the application
CMD ["python", "location.py"]
