from flask import Flask, render_template, request, jsonify
from solver import solve_module1, solve_module3
import traceback

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/module1', methods=['POST'])
def module1_api():
    try:
        data = request.json
        C = float(data.get('C', 0))
        phi = float(data.get('phi', 0))
        gamma = float(data.get('gamma', 0))
        B = float(data.get('B', 0))
        L = float(data.get('L', 0))
        Df = float(data.get('Df', 0))
        F = float(data.get('F', 0))
        FS = float(data.get('FS', 3.0))

        result = solve_module1(C, phi, gamma, B, L, Df, F, FS)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/module3', methods=['POST'])
def module3_api():
    try:
        data = request.json
        grs_data = data.get('grs_data')
        EA = float(data.get('EA', 0))
        UZ_ALLOW = float(data.get('UZ_ALLOW', 0))

        result = solve_module3(grs_data, EA, UZ_ALLOW)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
