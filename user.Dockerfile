# Build conda environment
FROM condaforge/miniforge3:24.3.0-0 as conda

COPY environment.yml /tmp/environment.yml

RUN CONDA_COPY_ALWAYS=true mamba env create -p /env -f /tmp/environment.yml \
  && conda clean -afy


SHELL ["mamba", "run", "--no-capture-output", "-p", "/env", "/bin/bash", "-c"]
RUN python -m ensurepip --upgrade
RUN pip3 install --upgrade pip
RUN pip install setuptools
COPY . /code
RUN pip3 install --no-deps /code

# Create image
FROM python:3.12-slim

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

COPY --from=conda /env /env

RUN apt-get update && apt-get upgrade && apt-get clean

RUN apt-get install -y ca-certificates
# Create a new user with UID 1000
RUN useradd -m -u 1000 -s /bin/bash conda-user
RUN mkdir /quetz-deployment
RUN chown -R conda-user:conda-user /quetz-deployment

# Set the default user
USER conda-user

# Set WORKDIR to /tmp because quetz always creates a quetz.log file
# in the current directory
WORKDIR /tmp
ENV PATH /env/bin:$PATH
EXPOSE 8000

CMD ["quetz", "run", "/quetz-deployment", "--host", "0.0.0.0", "--port", "8000"]
