.PHONY: install update run enroll debug help

help:
	@echo "face_recog — targets:"
	@echo "  make install   — buat conda env dari environment.yml"
	@echo "  make update    — update conda env"
	@echo "  make run       — jalankan pipeline (recognize + presence + alert)"
	@echo "  make enroll    — enroll SPG 001 (30 samples). Custom: python -m src.app enroll --spg_id ID --name NAMA --samples N"
	@echo "  make debug     — preview webcam + face detection bbox"
	@echo "  make simulate  — run multi-camera simulation (2 cams) with loop video"
	@echo "  make simulate-light — run simulation without preview (save resources)"

install:
	conda env create -f environment.yml

update:
	conda env update -f environment.yml --prune

run:
	python -m src.app run

enroll:
	python -m src.app enroll --spg_id 001 --name "Nana" --samples 30

debug:
	python -m src.app debug

simulate:
	@echo "Running Multi-Camera Simulation with Preview..."
	python -m src.commands.run_outlet sample_video/testing_kantor.mp4 sample_video/testing_kantor.mp4

simulate-light:
	@echo "Running Multi-Camera Simulation (No Preview)..."
	python -m src.commands.run_outlet sample_video/testing_kantor.mp4 sample_video/testing_kantor.mp4 --no-preview
