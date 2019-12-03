case ${{ matrix.os }} in
    windows*)
        eval "$(${CONDA}/condabin/conda.bat shell.bash hook)";;
    macOS*)
        eval "$(${CONDA}/condabin/conda shell.bash hook)";;
    *)
        eval "$(conda shell.bash hook)";;
esac

if [ -d ${CONDA}/envs/test ]; then
    conda activate test
else
    conda activate
fi

