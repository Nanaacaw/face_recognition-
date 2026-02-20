.PHONY: install update run enroll debug help simulate simulate-light dashboard webcam

help:
	@echo "face_recog — targets:"
	@echo "  make install        — buat conda env dari environment.yml"
	@echo "  make update         — update conda env"
	@echo "  make webcam         — single webcam testing (uses camera: config)"
	@echo "  make run            — production multi-camera RTSP (uses outlet: config)"
	@echo "  make enroll         — enroll SPG 001 (30 samples)"
	@echo "  make debug          — preview webcam + face detection bbox"
	@echo "  make simulate       — simulation with preview windows"
	@echo "  make simulate-light — simulation without preview (save resources)"
	@echo "  make dashboard      — start Monitoring Dashboard (FastAPI + Tailwind)"

install:
	conda env create -f environment.yml

update:
	conda env update -f environment.yml --prune

webcam:
	python -m src.app run

run:
	@echo "Starting Multi-Camera RTSP Monitoring (Production)..."
	python -m src.commands.run_outlet

enroll:
	python -m src.app enroll --spg_id 001 --name "Nana" --samples 30

debug:
	python -m src.app debug

simulate:
	@echo "Running Simulation with Preview (video files)..."
	python -m src.commands.run_outlet --simulate --preview

simulate-light:
	@echo "Running Simulation without Preview (video files)..."
	python -m src.commands.run_outlet --simulate --no-preview

dashboard:
	@echo "Starting Dashboard on http://localhost:8000 ..."
	python -m src.frontend.main
