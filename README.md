# GDS II viewer bas on three-cad-viewer

## Usage

- Prepare Python:

    ```bash
    # create a fresh Python environment and activate it

    pip install -r requirements.txt
    ```

- Create the example (optional, the js files are already in viewer.js):

    ```bash
    # 1 = gf component example
    python to_cell_json.py 1
    # 2 = sky130 example
    python to_cell_json.py 2
    ```

    This will store the javascript files into viewer/js

- View the results:

    ```bash
    cd viewer
    python -m http.server
    ```

    and open the browser at http://localhost:8000
