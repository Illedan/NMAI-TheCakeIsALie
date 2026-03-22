CXX      := g++
CXXFLAGS := -O2 -std=c++17 -Wall
TARGET   := sim
SRC      := sim.cpp
JSON_HDR := nlohmann/json.hpp

.PHONY: all clean

all: $(TARGET)

# Download nlohmann/json single-header if not present
$(JSON_HDR):
	mkdir -p nlohmann
	curl -sSL https://github.com/nlohmann/json/releases/download/v3.11.3/json.hpp \
	     -o $(JSON_HDR)

$(TARGET): $(SRC) $(JSON_HDR)
	$(CXX) $(CXXFLAGS) -I. -o $@ $<

clean:
	rm -f $(TARGET)
