source venv/bin/activate

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
export PATH=$DIR/node_modules/.bin/:$PATH
