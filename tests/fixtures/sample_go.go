// Sample Go file used as a test fixture for the AST parser.
// Tests that the older tree-sitter grammar handles structs and methods.

package main

import "fmt"

// UserConfig holds user configuration.
type UserConfig struct {
	Name  string
	Email string
	Roles []string
}

// DatabaseOptions holds database connection settings.
type DatabaseOptions struct {
	Host string
	Port int
	SSL  bool
}

// NewUserConfig creates a new UserConfig with defaults.
func NewUserConfig(name, email string) *UserConfig {
	return &UserConfig{
		Name:  name,
		Email: email,
		Roles: []string{"user"},
	}
}

// Greet returns a greeting string.
func (u *UserConfig) Greet() string {
	return fmt.Sprintf("Hello, %s!", u.Name)
}

// ConnectionString builds a DSN from database options.
func (d *DatabaseOptions) ConnectionString() string {
	scheme := "postgres"
	if d.SSL {
		scheme = "postgres+ssl"
	}
	return fmt.Sprintf("%s://%s:%d", scheme, d.Host, d.Port)
}

func main() {
	user := NewUserConfig("Alice", "alice@example.com")
	fmt.Println(user.Greet())
}
