# -VAXGUARD-IoT
VAXGUARD - IoT Engineering Project
# VaxGuard-AI: IoT-Based Healthcare Asset Safety System

## Project Overview
VaxGuard-AI is an IoT-based healthcare project designed to improve medical inventory security and patient safety. It aims to help prevent incorrect medical asset allocation, monitor storage conditions, and detect unauthorized inventory removal.

The system combines embedded hardware, sensor monitoring, and a software dashboard for medical asset management.

## Problem Statement
Traditional inventory systems may record stock levels without verifying whether the correct medical asset is assigned to the intended patient. They may also fail to detect unsafe storage temperatures or unauthorized removal of medical items.

VaxGuard-AI aims to address these challenges through automated verification and real-time monitoring.

## Objectives
- Improve medical asset tracking and inventory security.
- Support staff authentication using RFID.
- Monitor medical storage conditions using temperature sensors.
- Detect unauthorized asset removal using inventory monitoring.
- Support patient-to-asset verification.
- Provide a dashboard for monitoring and managing system information.

## Hardware Components
The project report identifies the following components:

- ESP32 microcontroller
- RC522 RFID reader
- Temperature sensor
- Buzzer
- Breadboard and jumper wires



## Software and Technologies


- Arduino/C++ for embedded programming
- Python for backend application logic
- HTML, CSS and JavaScript for the web interface
- MQTT for IoT communication
- Database technology for storing records



## Working Principle
1. The IoT hardware collects information from connected sensors and RFID readers.
2. The system processes staff authentication and medical asset information.
3. Sensor readings help monitor storage conditions.
4. Inventory monitoring helps identify unexpected asset removal.
5. The software application supports medical asset verification and monitoring.
6. The dashboard presents relevant information to the user.

## Project Files
- `sketch_jun5a.ino` — Arduino source code.
- `app.py` — Python application
- `templates/dashboard.html` — Dashboard interface

## Project Report
The detailed project report can be added separately to this repository if required.

## Project Purpose
VaxGuard-AI explores how IoT and software-based verification can help improve healthcare inventory management and medical asset safety.
