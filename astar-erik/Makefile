CXX = g++
CXXFLAGS = -std=c++17 -O2 -Wall -Wextra
TARGET = astar
SRCS = main.cpp infra.cpp simulator.cpp solution.cpp hillclimb.cpp agent.cpp
OBJS = $(SRCS:.cpp=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^

%.o: %.cpp infra.h simulator.h hillclimb.h agent.h
	$(CXX) $(CXXFLAGS) -c $< -o $@

run: $(TARGET)
	./$(TARGET) --base ../astar-island --view view

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all run clean
