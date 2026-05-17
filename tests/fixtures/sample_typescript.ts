// Sample TypeScript file used as a test fixture for the AST parser.
// Tests that the older tree-sitter grammar handles interfaces correctly.

interface UserConfig {
    name: string;
    email: string;
    roles: string[];
}

interface DatabaseOptions {
    host: string;
    port: number;
    ssl: boolean;
}

function createUser(config: UserConfig): void {
    console.log(`Creating user: ${config.name}`);
}

class AuthService {
    private token: string | null = null;

    constructor(private readonly baseUrl: string) {}

    async login(email: string, password: string): Promise<string> {
        const response = await fetch(`${this.baseUrl}/login`, {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        const data = await response.json();
        this.token = data.token;
        return this.token;
    }

    logout(): void {
        this.token = null;
    }

    isAuthenticated(): boolean {
        return this.token !== null;
    }
}

const processConfig = (opts: DatabaseOptions): string => {
    return `${opts.host}:${opts.port}`;
};

export { UserConfig, DatabaseOptions, AuthService, createUser, processConfig };
