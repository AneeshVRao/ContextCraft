// Sample JavaScript file used as a test fixture for the AST parser.

import { readFile } from 'fs/promises';

function greet(name) {
    return `Hello, ${name}!`;
}

class Calculator {
    constructor(initial = 0) {
        this.value = initial;
    }

    add(x) {
        this.value += x;
        return this.value;
    }

    subtract(x) {
        this.value -= x;
        return this.value;
    }
}

const processFile = async (path) => {
    const content = await readFile(path, 'utf-8');
    return content;
};

export { greet, Calculator, processFile };
