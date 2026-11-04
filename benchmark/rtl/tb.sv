module tb;
  logic clk = 0;
  logic [31:0] a = 0, b = 0;
  logic [63:0] acc = 0, result, expected;
  longint unsigned state;
  int unsigned seed = 1;
  int unsigned cycles = 1000000;
  mac dut(.*);
  always #5 clk = ~clk;
  initial begin
    if ($value$plusargs("seed=%d", seed)) begin end
    if ($value$plusargs("cycles=%d", cycles)) begin end
    state = 64'(seed) + 1;
    for (int unsigned i = 0; i < cycles; i++) begin
      @(negedge clk);
      state ^= state << 13;
      state ^= state >> 7;
      state ^= state << 17;
      a = state[31:0];
      b = state[63:32];
      acc = 64'(i);
      expected = (64'(a) * 64'(b)) + acc;
      @(posedge clk);
      #1;
      if (result !== expected) $fatal(1, "Mismatch seed=%0d cycle=%0d", seed, i);
    end
    $display("POC_TEST_PASS seed=%0d cycles=%0d", seed, cycles);
    $finish;
  end
endmodule

