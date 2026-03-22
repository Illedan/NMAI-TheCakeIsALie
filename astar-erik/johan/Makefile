CXX      = g++
CXXFLAGS = -std=c++17 -O3 -march=native -Wall
TARGET   = solution

all: $(TARGET)

# infra compiles slowly (simulator + JSON), solution compiles fast
infra.o: infra.cpp infra.hpp
	$(CXX) $(CXXFLAGS) -c infra.cpp -o infra.o

solution.o: solution.cpp infra.hpp
	$(CXX) $(CXXFLAGS) -c solution.cpp -o solution.o

$(TARGET): infra.o solution.o
	$(CXX) $(CXXFLAGS) -o $@ $^ -lpthread

clean:
	rm -f *.o $(TARGET)

.PHONY: clean
