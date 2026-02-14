install:
	conda env create -f environment.yml

update:
	conda env update -f environment.yml --prune

enroll:
	python -m src.app enroll --spg_id 001 --name "Nana" --samples 30

run:
	python -m src.app run